"""ZIP archive ingestion — extract and classify files for the pipeline.

Handles ZIP uploads containing a mix of native EmotiBit channels,
native/pre-formatted Polar files, event markers, and Order & Affect CSVs.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field


@dataclass
class ZipContents:
    """Classification result from a ZIP archive."""

    # Native EmotiBit channels: suffix -> csv text
    emotibit_channels: dict[str, str] = field(default_factory=dict)
    # Pre-formatted EmotiBit CSV text (if found instead of native channels)
    emotibit_formatted: str | None = None
    # Polar CSV text (native or pre-formatted)
    polar_text: str | None = None
    # Event markers CSV text
    markers_text: str | None = None
    # Order & Affect CSV text
    order_affect_text: str | None = None
    # Files that could not be classified
    unclassified: list[str] = field(default_factory=list)
    # Whether the Polar file is native format
    polar_is_native: bool = False
    # Whether EmotiBit files are native format
    emotibit_is_native: bool = False


# Native EmotiBit channel suffix pattern: *_EA.csv, *_AX.csv, etc.
_EMOTIBIT_CHANNEL_RE = re.compile(r"_([AE][AXYZ])\.csv$", re.IGNORECASE)

# Filename patterns for classification
_POLAR_NAME_RE = re.compile(r"(polar|h10|hrv|ecg|rr)", re.IGNORECASE)
_MARKER_NAME_RE = re.compile(
    r"(marker|event|session_mark)", re.IGNORECASE
)
_ORDER_AFFECT_NAME_RE = re.compile(
    r"(order|affect|valence|arousal|condition)", re.IGNORECASE
)


def _sniff_header(text: str) -> set[str]:
    """Read the first line of CSV text and return lowercase column names."""
    first_line = text.split("\n", 1)[0]
    # Skip comment lines
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            first_line = stripped
            break
    return {c.strip().lower() for c in first_line.split(",")}


def extract_and_classify_zip(zip_bytes: bytes) -> ZipContents:
    """Extract a ZIP archive and classify each CSV file.

    Classification priority:
    1. Filename pattern matching (most reliable for native EmotiBit channels)
    2. Header column sniffing (for pre-formatted files)
    3. Fallback to unclassified

    Args:
        zip_bytes: raw bytes of the ZIP file.

    Returns:
        ZipContents with classified file texts.
    """
    result = ZipContents()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            # Skip directories and hidden files
            name = info.filename
            if info.is_dir() or name.startswith("__MACOSX") or name.startswith("."):
                continue
            basename = name.split("/")[-1]
            if not basename or basename.startswith("."):
                continue

            try:
                text = zf.read(name).decode("utf-8", errors="replace")
            except Exception:
                result.unclassified.append(basename)
                continue

            if not text.strip():
                continue

            headers = _sniff_header(text)

            # ---- 1. Native EmotiBit channel files ----
            channel_match = _EMOTIBIT_CHANNEL_RE.search(basename)
            if channel_match:
                suffix = channel_match.group(1).upper()
                result.emotibit_channels[suffix] = text
                result.emotibit_is_native = True
                continue

            # ---- 2. Header-based classification ----

            # Pre-formatted EmotiBit (timestamp_ms + eda_us)
            if "timestamp_ms" in headers and "eda_us" in headers:
                result.emotibit_formatted = text
                continue

            # Order & Affect
            if {"subject_id", "room_type"}.issubset(headers) or \
               {"subject_id", "valence", "arousal"}.issubset(headers) or \
               _ORDER_AFFECT_NAME_RE.search(basename):
                if any(h in headers for h in ("valence", "arousal", "room_type", "room_order")):
                    result.order_affect_text = text
                    continue

            # Event markers (session_id + event_code + utc_ms)
            if {"event_code", "utc_ms"}.issubset(headers) or \
               _MARKER_NAME_RE.search(basename):
                result.markers_text = text
                continue

            # Native Polar (utc_epoch_ns)
            if "utc_epoch_ns" in headers:
                result.polar_text = text
                result.polar_is_native = True
                continue

            # Pre-formatted Polar (timestamp_ms/timestamp_ns + hr_bpm/rr_ms/ecg)
            polar_signals = {"hr_bpm", "rr_ms", "ecg_uv", "ecg_mv", "ecg",
                             "raw_ecg", "raw_ecg_uv", "voltage_uv"}
            if headers.intersection(polar_signals) or \
               ("timestamp_ns" in headers and headers.intersection({"rr_ms", "rr"})):
                result.polar_text = text
                continue

            # Filename-based fallback
            if _POLAR_NAME_RE.search(basename):
                result.polar_text = text
                continue

            result.unclassified.append(basename)

    return result
