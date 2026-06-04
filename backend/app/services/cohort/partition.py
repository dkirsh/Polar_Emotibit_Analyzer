"""Subject-aware ingestion for the cohort pipeline.

Walks a directory (or a ZIP archive) and partitions every file into a
``SubjectBundle`` keyed by detected subject. Returns an ``IngestionReport``
that surfaces what was found, what was ambiguous, and what the wizard
layer needs to ask the operator.

Subject-id detection runs in priority order:

1. **Explicit manifest** — a ``subjects.json`` or ``manifest.csv`` at the
   directory root that maps file paths or folder names to subject ids.
   Highest authority; overrides everything else. Wizard writes here.
2. **Enclosing folder name** — e.g. ``sub_1.1_G1/`` or ``Subject_03/``.
   Pattern-matched against several conventions.
3. **Filename pattern** — e.g. ``1.1_G1_2025-05-11_..._HR.csv``. Fallback
   when the folder is generic.
4. **None of the above** — the file lands in ``unassigned`` with a
   wizard question prompted ("which subject does this file belong to?").

The native-EmotiBit channel map is extended here to cover **all 26
channels** the EmotiBit emits, not just the four (EA/AX/AY/AZ) the
upstream analyzer recognizes today. See ``NATIVE_EMOTIBIT_CHANNEL_MAP``.

Per the design note in ``__init__``: this module is purely additive —
it does not import from ``app.services.ingestion.zip_ingestion`` and is
not imported by it.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Extended native EmotiBit channel map
# ---------------------------------------------------------------------------
# The full set of two-letter codes that the EmotiBit firmware emits, mapped
# to schema names suitable for downstream merging. Order is significant only
# in the sense that EA is the natural timeline anchor (highest-rate continuous
# signal). The upstream analyzer's restricted four-channel map is preserved
# as a subset for backward compatibility.
#
# Categories:
#   Cardiac:     HR, BI, PG, PI, PR
#   EDA:         EA, EL, EM, SA, SR, SF
#   Temperature: T1, TH, TL
#   Motion:      AX, AY, AZ, AK, GX, GY, GZ, MX, MY, MZ
#   Meta:        BV, BP (battery %), RB, RD
#
# Some lab exports use ``B%`` for battery percent; we accept it as an alias
# of ``BP``.

NATIVE_EMOTIBIT_CHANNEL_MAP: dict[str, str] = {
    # ---- Cardiac ----
    "HR": "heart_rate_bpm",
    "BI": "beat_interval_ms",
    "PG": "ppg_green",
    "PI": "ppg_infrared",
    "PR": "ppg_red",
    # ---- Electrodermal ----
    "EA": "eda_us",
    "EL": "eda_level_us",
    "EM": "eda_metric",  # firmware-derived EDA aggregate
    "SA": "skin_conductance_a",
    "SR": "skin_resistance_kohm",
    "SF": "skin_conductance_f",
    # ---- Temperature ----
    "T1": "skin_temp_c",
    "TH": "thermopile_c",
    "TL": "temp_low",
    # ---- Motion ----
    "AX": "acc_x",
    "AY": "acc_y",
    "AZ": "acc_z",
    "AK": "acc_magnitude",
    "GX": "gyro_x",
    "GY": "gyro_y",
    "GZ": "gyro_z",
    "MX": "mag_x",
    "MY": "mag_y",
    "MZ": "mag_z",
    # ---- Meta ----
    "BV": "battery_voltage",
    "BP": "battery_percent",
    "RB": "raw_button",
    "RD": "raw_diag",
}

# Aliases accepted in filenames but mapped to the canonical suffix.
_CHANNEL_SUFFIX_ALIASES = {
    "B%": "BP",
    "BPCT": "BP",
}

# Filename-suffix regex: matches "_HR.csv", "_B%.csv", "_AX.csv", etc.
_CHANNEL_SUFFIX_RE = re.compile(
    r"_([A-Z][A-Z0-9%]{1,3})\.csv$", re.IGNORECASE
)

# Subject-id patterns recognized in folder names and filenames.
# Each pattern produces (subject_id, group_id_or_none).
_SUBJECT_PATTERNS = [
    # sub_1.1_G1  /  sub_1.10_G1  /  sub_1.16_G4
    re.compile(r"sub_(?P<sid>\d+(?:\.\d+)?)_G(?P<gid>\d+)", re.IGNORECASE),
    # 1.1_G1 (folder or filename prefix without sub_ prefix)
    re.compile(r"(?:^|[_/])(?P<sid>\d+\.\d+)_G(?P<gid>\d+)", re.IGNORECASE),
    # Subject_03_G2 / subject03_G2
    re.compile(r"subject[_]?(?P<sid>\d+(?:\.\d+)?)_G(?P<gid>\d+)", re.IGNORECASE),
    # Bare subject id without group (low confidence)
    re.compile(r"(?:^|[_/])sub_(?P<sid>\d+(?:\.\d+)?)(?:_|$)", re.IGNORECASE),
    re.compile(r"(?:^|[_/])(?P<sid>\d+\.\d+)(?:_|$)"),
]

# Filename hints for non-EmotiBit file types.
_POLAR_NAME_RE = re.compile(r"(polar|h10|hrv|ecg|rr)\b", re.IGNORECASE)
_MARKER_NAME_RE = re.compile(r"(marker|event|session_mark)", re.IGNORECASE)
_ORDER_AFFECT_NAME_RE = re.compile(r"(order|affect|valence|arousal|condition)", re.IGNORECASE)
_RESPIRATORY_NAME_RE = re.compile(
    r"(respirat|vernier_belt|clean_respiratory_data|breath)", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Data carriers
# ---------------------------------------------------------------------------


@dataclass
class SubjectBundle:
    """All files belonging to one detected subject."""

    subject_id: str
    group_id: str | None = None
    detection_source: str = ""  # "manifest" | "folder" | "filename" | "manual"
    detection_confidence: float = 1.0  # 0..1

    # Channel files: suffix → list of file paths (usually 1; >1 = duplicate)
    emotibit_channels: dict[str, list[Path]] = field(default_factory=dict)
    # Pre-formatted single CSV (timestamp_ms + eda_us schema)
    emotibit_formatted: list[Path] = field(default_factory=list)

    polar_files: list[Path] = field(default_factory=list)
    markers_files: list[Path] = field(default_factory=list)
    order_affect_files: list[Path] = field(default_factory=list)
    respiratory_files: list[Path] = field(default_factory=list)

    other_files: list[Path] = field(default_factory=list)

    # Provenance / debugging
    folder_paths: list[Path] = field(default_factory=list)
    earliest_mtime: datetime | None = None

    # Wizard-flagged questions specific to this subject
    questions: list[str] = field(default_factory=list)

    def n_files(self) -> int:
        n = sum(len(v) for v in self.emotibit_channels.values())
        n += len(self.emotibit_formatted)
        n += len(self.polar_files)
        n += len(self.markers_files)
        n += len(self.order_affect_files)
        n += len(self.respiratory_files)
        n += len(self.other_files)
        return n

    def summary_dict(self) -> dict:
        return dict(
            subject_id=self.subject_id,
            group_id=self.group_id,
            detection_source=self.detection_source,
            detection_confidence=self.detection_confidence,
            n_emotibit_channels=len(self.emotibit_channels),
            emotibit_channel_codes=sorted(self.emotibit_channels.keys()),
            n_emotibit_formatted=len(self.emotibit_formatted),
            n_polar=len(self.polar_files),
            n_markers=len(self.markers_files),
            n_respiratory=len(self.respiratory_files),
            n_order_affect=len(self.order_affect_files),
            n_other=len(self.other_files),
            n_files_total=self.n_files(),
            n_questions=len(self.questions),
            folder_paths=[str(p) for p in self.folder_paths],
        )


@dataclass
class IngestionReport:
    """Result of partitioning a directory or ZIP."""

    root: str
    subjects: list[SubjectBundle]
    unassigned: list[tuple[Path, str]] = field(default_factory=list)
    # (subject_id, channel_suffix, list_of_file_paths) for files that would
    # overwrite each other under the legacy analyzer's single-slot model.
    duplicates: list[tuple[str, str, list[Path]]] = field(default_factory=list)
    # Free-form warnings about the data
    warnings: list[str] = field(default_factory=list)
    # Questions the wizard should ask the operator before processing
    wizard_questions: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return dict(
            root=self.root,
            n_subjects=len(self.subjects),
            n_unassigned_files=len(self.unassigned),
            n_duplicate_collisions=len(self.duplicates),
            n_warnings=len(self.warnings),
            n_wizard_questions=len(self.wizard_questions),
            subjects=[s.summary_dict() for s in self.subjects],
        )


# ---------------------------------------------------------------------------
# Subject-id detection
# ---------------------------------------------------------------------------


def _normalize_subject_id(raw_sid: str) -> str:
    """Canonical subject id form (string, leading-zero-stripped numeric parts)."""
    s = raw_sid.strip()
    # If purely numeric/dotted, drop leading zeros per part: "01.05" → "1.5"
    if re.match(r"^\d+(\.\d+)?$", s):
        parts = s.split(".")
        parts = [str(int(p)) if p.isdigit() else p for p in parts]
        return ".".join(parts)
    return s


def _detect_subject_from_text(text: str) -> tuple[str, str | None, float] | None:
    """Try the patterns against ``text`` (a folder name or filename).

    Returns (subject_id, group_id, confidence) or None.
    """
    for i, pat in enumerate(_SUBJECT_PATTERNS):
        m = pat.search(text)
        if m:
            sid = _normalize_subject_id(m.group("sid"))
            gid = m.groupdict().get("gid")
            gid = f"G{gid}" if gid else None
            # First pattern is the highest-confidence "sub_X.Y_GZ" canonical form
            confidence = max(0.4, 1.0 - 0.15 * i)
            return sid, gid, confidence
    return None


def _detect_subject_for_path(path: Path, root: Path) -> tuple[str, str | None, float, str] | None:
    """Walk up the directory hierarchy looking for a subject identifier.

    Returns (subject_id, group_id, confidence, detection_source) or None.
    Priority: enclosing folder names (parent → ancestor), then the filename
    itself.
    """
    rel = path.relative_to(root) if path.is_absolute() and root in path.parents or path == root else None
    try:
        rel_parts = list(path.relative_to(root).parts[:-1])  # excludes basename
    except (ValueError, RuntimeError):
        rel_parts = []
    # Walk closest-folder-first
    for part in reversed(rel_parts):
        hit = _detect_subject_from_text(part)
        if hit:
            sid, gid, conf = hit
            return sid, gid, conf, f"folder:{part}"
    # Fallback to filename
    hit = _detect_subject_from_text(path.name)
    if hit:
        sid, gid, conf = hit
        return sid, gid, max(0.3, conf - 0.2), f"filename:{path.name}"
    return None


# ---------------------------------------------------------------------------
# File classification
# ---------------------------------------------------------------------------


def _classify_file(path: Path) -> str:
    """Return a coarse type: "emotibit_channel" | "emotibit_formatted" |
    "polar" | "markers" | "order_affect" | "respiratory" | "other"."""
    name = path.name
    # 1. Native EmotiBit channel (highest-priority match)
    m = _CHANNEL_SUFFIX_RE.search(name)
    if m:
        suffix = m.group(1).upper()
        suffix = _CHANNEL_SUFFIX_ALIASES.get(suffix, suffix)
        if suffix in NATIVE_EMOTIBIT_CHANNEL_MAP:
            return "emotibit_channel"
    # 2. Respiratory (Vernier belt)
    if _RESPIRATORY_NAME_RE.search(name):
        return "respiratory"
    # 3. Markers
    if _MARKER_NAME_RE.search(name):
        return "markers"
    # 4. Order & Affect
    if _ORDER_AFFECT_NAME_RE.search(name):
        return "order_affect"
    # 5. Polar
    if _POLAR_NAME_RE.search(name):
        return "polar"
    # 6. Pre-formatted EmotiBit single CSV — would need header sniffing to
    #    confirm; we leave that to the orchestrator. For partition we tag
    #    as "other" unless filename hints (rare).
    return "other"


def _extract_channel_suffix(path: Path) -> str | None:
    m = _CHANNEL_SUFFIX_RE.search(path.name)
    if not m:
        return None
    suffix = m.group(1).upper()
    return _CHANNEL_SUFFIX_ALIASES.get(suffix, suffix)


# ---------------------------------------------------------------------------
# Optional manifest support
# ---------------------------------------------------------------------------

# A manifest file lets the operator override detection. Two formats accepted:
#
#  subjects.json:
#    {
#      "subjects": [
#        {"subject_id": "1.1", "group_id": "G1",
#         "neurotype_label": "control",
#         "include_paths": ["sub_1.1_G1/"]},
#        ...
#      ]
#    }
#
#  manifest.csv:
#    subject_id,group_id,neurotype_label,path_glob
#    1.1,G1,control,sub_1.1_G1/**
#    ...

_MANIFEST_NAMES = ("subjects.json", "manifest.csv")


def _load_manifest(root: Path) -> dict | None:
    for name in _MANIFEST_NAMES:
        path = root / name
        if not path.exists():
            continue
        try:
            if name.endswith(".json"):
                with open(path) as f:
                    return json.load(f)
            else:
                import csv
                rows = []
                with open(path) as f:
                    for r in csv.DictReader(f):
                        rows.append(r)
                return {"subjects": rows, "format": "csv"}
        except Exception as exc:
            log.warning("Could not parse manifest %s: %s", path, exc)
    return None


# ---------------------------------------------------------------------------
# Walker
# ---------------------------------------------------------------------------


def _file_iter(root: Path) -> Iterable[Path]:
    """Yield every regular file under root, skipping hidden + macOS junk."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Filter hidden directories in-place
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__MACOSX"]
        for fname in filenames:
            if fname.startswith(".") or fname.startswith("~$"):
                continue
            yield Path(dirpath) / fname


def _md5(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(chunk), b""):
            h.update(c)
    return h.hexdigest()


def partition_directory(root: str | Path, *,
                         use_manifest: bool = True,
                         detect_byte_duplicates: bool = True,
                         ) -> IngestionReport:
    """Walk ``root`` recursively, partition every file into ``SubjectBundle``s.

    Args:
        root: directory to walk.
        use_manifest: honor ``subjects.json`` or ``manifest.csv`` at root.
        detect_byte_duplicates: MD5 same-channel files within a subject to
            flag the 1.11/1.12-style data-integrity issue.
    """
    root_path = Path(root).resolve()
    report = IngestionReport(root=str(root_path), subjects=[])

    if not root_path.exists():
        report.warnings.append(f"Root does not exist: {root_path}")
        return report
    if not root_path.is_dir():
        report.warnings.append(f"Root is not a directory: {root_path}")
        return report

    bundles_by_sid: dict[str, SubjectBundle] = {}

    manifest = _load_manifest(root_path) if use_manifest else None
    manifest_map: dict[str, tuple[str, str | None]] = {}
    if manifest:
        for s in manifest.get("subjects", []):
            sid = _normalize_subject_id(s.get("subject_id", ""))
            gid = s.get("group_id") or None
            paths = s.get("include_paths") or [s.get("path_glob")]
            for p in paths:
                if p:
                    manifest_map[str(p).rstrip("/")] = (sid, gid)

    file_count = 0
    for path in _file_iter(root_path):
        file_count += 1
        # 1. Try manifest override
        sid: str | None = None
        gid: str | None = None
        conf = 1.0
        source = ""
        if manifest_map:
            rel = str(path.relative_to(root_path))
            for key, (m_sid, m_gid) in manifest_map.items():
                if rel.startswith(key):
                    sid, gid, conf, source = m_sid, m_gid, 1.0, f"manifest:{key}"
                    break
        # 2. Try folder + filename detection
        if sid is None:
            hit = _detect_subject_for_path(path, root_path)
            if hit:
                sid, gid, conf, source = hit
        # 3. Could not infer
        if sid is None:
            report.unassigned.append((path, "no subject identifier in folder or filename"))
            continue

        bundle = bundles_by_sid.get(sid)
        if bundle is None:
            bundle = SubjectBundle(subject_id=sid, group_id=gid,
                                   detection_source=source,
                                   detection_confidence=conf)
            bundles_by_sid[sid] = bundle
        # Reconcile group_id (manifest wins; otherwise take first non-null)
        if gid and (bundle.group_id is None or source.startswith("manifest")):
            bundle.group_id = gid
        # Reconcile confidence (keep the max — most trustworthy)
        if conf > bundle.detection_confidence:
            bundle.detection_confidence = conf
        # Track folders this subject's data appeared in
        parent = path.parent
        if parent not in bundle.folder_paths:
            bundle.folder_paths.append(parent)

        # Classify file
        kind = _classify_file(path)
        if kind == "emotibit_channel":
            suffix = _extract_channel_suffix(path) or "?"
            bundle.emotibit_channels.setdefault(suffix, []).append(path)
        elif kind == "polar":
            bundle.polar_files.append(path)
        elif kind == "markers":
            bundle.markers_files.append(path)
        elif kind == "order_affect":
            bundle.order_affect_files.append(path)
        elif kind == "respiratory":
            bundle.respiratory_files.append(path)
        else:
            bundle.other_files.append(path)

    report.subjects = sorted(bundles_by_sid.values(),
                              key=lambda b: (
                                  # Numeric-first sort for ids like "1.1", "1.10"
                                  tuple(int(p) if p.isdigit() else p for p in b.subject_id.split(".")),
                                  b.subject_id,
                              ))

    # Duplicate detection: same channel suffix, multiple files within a subject
    for bundle in report.subjects:
        for suffix, files in bundle.emotibit_channels.items():
            if len(files) > 1:
                report.duplicates.append((bundle.subject_id, suffix, list(files)))
                bundle.questions.append(
                    f"Channel {suffix} has {len(files)} files; which is canonical? "
                    f"{[p.name for p in files]}"
                )

    # Byte-identical cross-subject duplicates (the 1.11/1.12 finding).
    # Aggregate by SUBJECT-PAIR so the wizard asks one question per pair, not
    # one question per duplicated file. Carries the full list for the report.
    if detect_byte_duplicates and len(report.subjects) > 1:
        digest_index: dict[str, list[tuple[str, Path]]] = {}
        for bundle in report.subjects:
            for files in bundle.emotibit_channels.values():
                for p in files:
                    try:
                        d = _md5(p)
                        digest_index.setdefault(d, []).append((bundle.subject_id, p))
                    except Exception:
                        continue
            for p in bundle.respiratory_files + bundle.polar_files:
                try:
                    d = _md5(p)
                    digest_index.setdefault(d, []).append((bundle.subject_id, p))
                except Exception:
                    continue
        # Group dup-files by subject-pair
        pair_dups: dict[tuple[str, ...], list[list[Path]]] = {}
        for d, entries in digest_index.items():
            sids = tuple(sorted({sid for sid, _ in entries}))
            if len(sids) > 1:
                pair_dups.setdefault(sids, []).append([p for _, p in entries])
        for sids, file_lists in pair_dups.items():
            n_dup = len(file_lists)
            # Capture which channels/file-kinds are affected so the operator
            # can see scope at a glance.
            kinds: list[str] = []
            for files in file_lists:
                kinds.append(files[0].name.split("_")[-1].replace(".csv", ""))
            kind_summary = ", ".join(sorted(set(kinds))[:8])
            if len(set(kinds)) > 8:
                kind_summary += ", …"
            report.warnings.append(
                f"BYTE-IDENTICAL files across subjects {list(sids)}: "
                f"{n_dup} duplicate files spanning channels {{{kind_summary}}}. "
                f"Strong evidence one folder is mislabelled. "
                f"Example: {file_lists[0][0]} vs {file_lists[0][1]}"
            )
            report.wizard_questions.append(
                f"Subjects {list(sids)} share {n_dup} byte-identical files "
                f"({kind_summary}). One folder is mislabelled — which subject "
                f"do these files actually belong to? "
                f"(Options: keep both subjects but tag one as 'suspect_duplicate'; "
                f"drop one subject; rename one subject; manual triage.)"
            )

    # Surface bundles with low confidence as questions
    for bundle in report.subjects:
        if bundle.detection_confidence < 0.6:
            report.wizard_questions.append(
                f"Subject {bundle.subject_id} was inferred with confidence "
                f"{bundle.detection_confidence:.2f} from {bundle.detection_source}. "
                f"Confirm or correct."
            )
        if bundle.group_id is None:
            report.wizard_questions.append(
                f"Subject {bundle.subject_id} has no group code (G1/G2/G3/G4). "
                f"Assign one or confirm 'no group'."
            )

    if file_count == 0:
        report.warnings.append("No files found under root.")

    return report


# ---------------------------------------------------------------------------
# ZIP entry point
# ---------------------------------------------------------------------------


def partition_zip(zip_bytes: bytes, *, use_manifest: bool = True,
                  detect_byte_duplicates: bool = True) -> IngestionReport:
    """Extract a ZIP to a temp dir and run ``partition_directory`` on it.

    For huge zips this is intentionally simple — extract once, walk once.
    A streaming variant could be added later if memory becomes a concern.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if info.filename.startswith("__MACOSX") or "/." in info.filename:
                    continue
                target = tmp_path / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    dst.write(src.read())
        report = partition_directory(tmp_path,
                                      use_manifest=use_manifest,
                                      detect_byte_duplicates=detect_byte_duplicates)
        # Replace temp paths with original archive-relative paths so the
        # report is meaningful after the temp dir is cleaned up.
        # (We just record the basename + arcname for downstream use.)
        report.warnings.append(
            "ZIP extraction used temp dir; file paths in the report are "
            "now relative to that temp dir. Use ``partition_directory`` "
            "directly on an extracted folder for persistent paths."
        )
        return report


__all__ = [
    "SubjectBundle",
    "IngestionReport",
    "NATIVE_EMOTIBIT_CHANNEL_MAP",
    "partition_directory",
    "partition_zip",
]
