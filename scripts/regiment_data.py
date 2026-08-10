#!/usr/bin/env python3
"""Regiment heterogeneous EmotiBit/Polar/marker recordings into one canonical store.

Different recorders use different conventions. Observed so far:
  - Marker file with point events, "active-until-next" semantics (no _onset/_offset).
  - Marker file with explicit X_onset / X_offset pairs.
  - Polar timestamps in ms (timestamp_ms) OR ns (timestamp_ns).
  - EmotiBit with or without accelerometer columns.

This tool INFERS each of those per session and normalises everything to one
canonical SQLite database in which:
  - all physiological timestamps are UTC milliseconds (`t_ms`);
  - every condition is an explicit window row `(label, onset_ms, offset_ms)`,
    regardless of whether the source used pairs or active-until-next;
  - provenance (source filenames, SHA-256, detected format) is recorded so the
    normalisation is auditable and reproducible.

Design follows the repo discipline: additive, dry-run-first, idempotent
(re-running replaces a session's rows, never duplicates), and it never silently
drops a marker column — anything it cannot interpret is reported.

Usage:
  python scripts/regiment_data.py --session SID --emotibit E.csv --polar P.csv --markers M.csv --db out.db
  python scripts/regiment_data.py --batch-dir DIR --db out.db          # auto-group by participant token
  python scripts/regiment_data.py ... --dry-run                        # report plan, write nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

# Epoch sanity bounds (ms): ~2001-09 .. ~2065. Used to detect timestamp units.
_MS_LO, _MS_HI = 1_000_000_000_000, 3_000_000_000_000


# ── format inference ─────────────────────────────────────────────────────────

def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV tolerant of non-UTF-8 marker files (e.g. a latin-1 '·')."""
    for enc in ("utf-8", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, encoding="utf-8", encoding_errors="replace")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _to_ms(series: pd.Series, col: str) -> tuple[pd.Series, str]:
    """Return (milliseconds, unit_detected). Uses the column name as a hint and
    the magnitude as a check, so a mislabelled column is still corrected."""
    s = pd.to_numeric(series, errors="coerce")
    med = float(s.dropna().median()) if s.notna().any() else 0.0
    name = col.lower()
    if "ns" in name or med > 1e17:
        return s / 1_000_000.0, "ns→ms"
    if "us" in name and "eda" not in name or (1e15 < med <= 1e17):
        return s / 1_000.0, "us→ms"
    return s, "ms"


def _detect_marker_convention(codes: list[str]) -> str:
    has_pairs = any(c.endswith("_onset") or c.endswith("_offset") for c in codes)
    return "onset_offset" if has_pairs else "active_until_next"


@dataclass
class SessionFiles:
    session_id: str
    emotibit: Path | None = None
    polar: Path | None = None
    markers: Path | None = None


@dataclass
class IngestReport:
    session_id: str
    polar_time_unit: str = ""
    marker_convention: str = ""
    n_eda: int = 0
    n_rr: int = 0
    n_events: int = 0
    duration_s: float = 0.0
    warnings: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)


# ── normalisation ────────────────────────────────────────────────────────────

def _normalise_events(mk: pd.DataFrame, session_end_ms: int | None) -> tuple[pd.DataFrame, str, list[str]]:
    """Return a canonical events frame (label, onset_ms, offset_ms, note) plus the
    detected convention and any warnings."""
    warnings: list[str] = []
    # accept aliases
    code_col = next((c for c in ("event_code", "event", "code", "marker", "label") if c in mk.columns), None)
    time_col = next((c for c in ("utc_ms", "time_ms", "timestamp_ms", "epoch_ms", "time") if c in mk.columns), None)
    if code_col is None or time_col is None:
        return pd.DataFrame(columns=["label", "onset_ms", "offset_ms", "note"]), "unknown", \
            [f"marker file missing code/time columns (have {list(mk.columns)})"]

    mk = mk.copy()
    mk["_code"] = mk[code_col].astype(str).str.strip()
    mk["_t"], _u = _to_ms(mk[time_col], time_col)
    mk = mk.dropna(subset=["_t"]).sort_values("_t").reset_index(drop=True)
    note_col = "note" if "note" in mk.columns else None
    codes = mk["_code"].tolist()
    convention = _detect_marker_convention(codes)

    rows: list[dict[str, Any]] = []
    if convention == "onset_offset":
        # pair X_onset with the next X_offset (by stripped base label)
        open_onsets: dict[str, float] = {}
        for _, r in mk.iterrows():
            code, t = r["_code"], float(r["_t"])
            if code.endswith("_onset"):
                open_onsets[code[: -len("_onset")]] = t
            elif code.endswith("_offset"):
                base = code[: -len("_offset")]
                if base in open_onsets:
                    rows.append({"label": base, "onset_ms": int(open_onsets.pop(base)), "offset_ms": int(t), "note": ""})
                else:
                    warnings.append(f"offset without matching onset: {code}")
            else:
                # a stray point marker inside an onset/offset file → treat as instant
                rows.append({"label": code, "onset_ms": int(t), "offset_ms": int(t), "note": ""})
        for base, t in open_onsets.items():
            warnings.append(f"onset without matching offset: {base}_onset")
    else:
        # active-until-next: each marker runs until the next marker; last to session end
        for i, r in mk.iterrows():
            onset = int(r["_t"])
            if i + 1 < len(mk):
                offset = int(mk.iloc[i + 1]["_t"])
            elif session_end_ms is not None:
                offset = int(session_end_ms)
            else:
                offset = onset
            note = str(r[note_col]) if note_col and pd.notna(r[note_col]) else ""
            rows.append({"label": r["_code"], "onset_ms": onset, "offset_ms": offset, "note": note})

    return pd.DataFrame(rows), convention, warnings


def ingest_session(sf: SessionFiles) -> tuple[dict[str, pd.DataFrame], IngestReport]:
    rep = IngestReport(session_id=sf.session_id)
    prov: dict[str, Any] = {}
    eda = pd.DataFrame(columns=["t_ms", "eda_us", "acc_x", "acc_y", "acc_z"])
    rr = pd.DataFrame(columns=["t_ms", "rr_ms", "hr_bpm"])
    events = pd.DataFrame(columns=["label", "onset_ms", "offset_ms", "note"])

    end_ms: int | None = None

    if sf.emotibit and sf.emotibit.exists():
        df = _read_csv(sf.emotibit)
        tcol = next((c for c in df.columns if "timestamp" in c.lower()), df.columns[0])
        t_ms, unit = _to_ms(df[tcol], tcol)
        eda = pd.DataFrame({"t_ms": t_ms})
        eda["eda_us"] = pd.to_numeric(df.get("eda_us"), errors="coerce")
        for a in ("acc_x", "acc_y", "acc_z"):
            eda[a] = pd.to_numeric(df[a], errors="coerce") if a in df.columns else None
        eda = eda.dropna(subset=["t_ms", "eda_us"])
        rep.n_eda = len(eda)
        end_ms = int(eda["t_ms"].max()) if len(eda) else None
        prov["emotibit"] = {"file": sf.emotibit.name, "sha256": _sha256(sf.emotibit), "ts_unit": unit, "cols": list(df.columns)}
        # surface any unused marker-like column rather than silently dropping it
        for c in df.columns:
            if re.search(r"marker|condition|trial|phase|event|label|block|segment", c, re.I):
                rep.warnings.append(f"emotibit column '{c}' looks like a marker but EmotiBit markers are not yet ingested inline")

    if sf.polar and sf.polar.exists():
        df = _read_csv(sf.polar)
        tcol = next((c for c in df.columns if "timestamp" in c.lower() or c.lower() in ("time",)), df.columns[0])
        t_ms, unit = _to_ms(df[tcol], tcol)
        rep.polar_time_unit = unit
        rr = pd.DataFrame({"t_ms": t_ms})
        rr["rr_ms"] = pd.to_numeric(df.get("rr_ms"), errors="coerce")
        rr["hr_bpm"] = pd.to_numeric(df["hr_bpm"], errors="coerce") if "hr_bpm" in df.columns else None
        rr = rr.dropna(subset=["t_ms"])
        rep.n_rr = int(rr["rr_ms"].notna().sum())
        if len(rr):
            end_ms = max(end_ms or 0, int(rr["t_ms"].max())) or end_ms
        prov["polar"] = {"file": sf.polar.name, "sha256": _sha256(sf.polar), "ts_unit": unit, "cols": list(df.columns)}

    if sf.markers and sf.markers.exists():
        mk = _read_csv(sf.markers)
        events, convention, warns = _normalise_events(mk, end_ms)
        rep.marker_convention = convention
        rep.n_events = len(events)
        rep.warnings.extend(warns)
        prov["markers"] = {"file": sf.markers.name, "sha256": _sha256(sf.markers), "convention": convention, "cols": list(mk.columns)}

    starts = [d["t_ms"].min() for d in (eda, rr) if len(d)]
    ends = [d["t_ms"].max() for d in (eda, rr) if len(d)]
    if starts and ends:
        rep.duration_s = round((max(ends) - min(starts)) / 1000.0, 1)
    rep.provenance = prov
    return {"eda": eda, "rr": rr, "events": events}, rep


# ── canonical store (SQLite) ─────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS session (
  session_id TEXT PRIMARY KEY, ingested_at TEXT, duration_s REAL,
  polar_time_unit TEXT, marker_convention TEXT, n_eda INTEGER, n_rr INTEGER,
  n_events INTEGER, warnings TEXT, provenance TEXT);
CREATE TABLE IF NOT EXISTS eda_sample (
  session_id TEXT, t_ms INTEGER, eda_us REAL, acc_x REAL, acc_y REAL, acc_z REAL);
CREATE TABLE IF NOT EXISTS rr_sample (
  session_id TEXT, t_ms INTEGER, rr_ms REAL, hr_bpm REAL);
CREATE TABLE IF NOT EXISTS event (
  session_id TEXT, label TEXT, onset_ms INTEGER, offset_ms INTEGER, note TEXT);
CREATE INDEX IF NOT EXISTS ix_eda ON eda_sample(session_id, t_ms);
CREATE INDEX IF NOT EXISTS ix_rr ON rr_sample(session_id, t_ms);
CREATE INDEX IF NOT EXISTS ix_ev ON event(session_id, onset_ms);
"""


def write_session(db: Path, frames: dict[str, pd.DataFrame], rep: IngestReport) -> None:
    con = sqlite3.connect(db)
    try:
        con.executescript(_SCHEMA)
        sid = rep.session_id
        # idempotent: clear any prior rows for this session before inserting
        for tbl in ("session", "eda_sample", "rr_sample", "event"):
            con.execute(f"DELETE FROM {tbl} WHERE session_id = ?", (sid,))
        con.execute(
            "INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sid, datetime.now(timezone.utc).isoformat(), rep.duration_s,
             rep.polar_time_unit, rep.marker_convention, rep.n_eda, rep.n_rr,
             rep.n_events, json.dumps(rep.warnings), json.dumps(rep.provenance)),
        )
        eda = frames["eda"].assign(session_id=sid)
        eda[["session_id", "t_ms", "eda_us", "acc_x", "acc_y", "acc_z"]].to_sql(
            "eda_sample", con, if_exists="append", index=False)
        rr = frames["rr"].assign(session_id=sid)
        rr[["session_id", "t_ms", "rr_ms", "hr_bpm"]].to_sql(
            "rr_sample", con, if_exists="append", index=False)
        ev = frames["events"].assign(session_id=sid)
        if len(ev):
            ev[["session_id", "label", "onset_ms", "offset_ms", "note"]].to_sql(
                "event", con, if_exists="append", index=False)
        con.commit()
    finally:
        con.close()


# ── grouping / CLI ───────────────────────────────────────────────────────────

def _classify(path: Path) -> str:
    n = path.name.lower()
    if "marker" in n or "event" in n:
        return "markers"
    if "polar" in n:
        return "polar"
    if "emotibit" in n:
        return "emotibit"
    return "unknown"


def _participant_token(path: Path) -> str:
    m = re.search(r"(p\d{3}|\d+\.\d+_G\d+)", path.name)
    return m.group(1) if m else path.stem


def discover_sessions(root: Path) -> list[SessionFiles]:
    groups: dict[str, SessionFiles] = {}
    for p in root.rglob("*.csv"):
        kind = _classify(p)
        if kind == "unknown":
            continue
        tok = _participant_token(p)
        sf = groups.setdefault(tok, SessionFiles(session_id=tok))
        setattr(sf, kind, p)
    return list(groups.values())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--session"); ap.add_argument("--emotibit", type=Path)
    ap.add_argument("--polar", type=Path); ap.add_argument("--markers", type=Path)
    ap.add_argument("--batch-dir", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.batch_dir:
        sessions = discover_sessions(args.batch_dir)
    else:
        if not args.session:
            ap.error("--session required when not using --batch-dir")
        sessions = [SessionFiles(args.session, args.emotibit, args.polar, args.markers)]

    print(f"Discovered {len(sessions)} session(s). dry-run={args.dry_run}")
    for sf in sorted(sessions, key=lambda s: s.session_id):
        frames, rep = ingest_session(sf)
        flag = "  ⚠ " + "; ".join(rep.warnings) if rep.warnings else ""
        print(f"  {rep.session_id:12s} polar_ts={rep.polar_time_unit or '-':6s} "
              f"markers={rep.marker_convention or '-':16s} "
              f"eda={rep.n_eda:6d} rr={rep.n_rr:5d} events={rep.n_events:3d} "
              f"dur={rep.duration_s:7.1f}s{flag}")
        if not args.dry_run:
            write_session(args.db, frames, rep)
    if not args.dry_run:
        print(f"Wrote canonical store → {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
