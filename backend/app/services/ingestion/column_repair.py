"""Column-repair suggestions for uploaded CSVs.

When a validation endpoint rejects a file because it lacks required columns,
this module compares the missing names against the columns that *are* present
using alias tables and fuzzy normalization.  The result is a list of
``{missing, found, confidence}`` dicts that the frontend can render as
"did you mean…?" hints.
"""

from __future__ import annotations

import re
from typing import Sequence

# ── Alias table ──────────────────────────────────────────────────────────
# Maps each canonical column name to a tuple of known aliases (all
# lower-cased). The first entry is always the canonical name itself.

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "eda_us": (
        "eda_us", "eda", "gsr", "skin_conductance", "sc",
        "eda_microsiemens",
    ),
    "timestamp_ms": (
        "timestamp_ms", "time_ms", "time", "timestamp", "ts",
        "epoch_ms", "unix_ms",
    ),
    "hr_bpm": (
        "hr_bpm", "hr", "heart_rate", "heartrate", "bpm",
    ),
    "rr_ms": (
        "rr_ms", "rr", "ibi", "ibi_ms", "rr_interval",
    ),
    "acc_x": (
        "acc_x", "accel_x", "ax", "accelerometer_x",
    ),
    "acc_y": (
        "acc_y", "accel_y", "ay", "accelerometer_y",
    ),
    "acc_z": (
        "acc_z", "accel_z", "az", "accelerometer_z",
    ),
    "event_code": (
        "event_code", "event", "code", "marker", "event_type",
    ),
    "utc_ms": (
        "utc_ms", "time_ms", "timestamp_ms", "epoch_ms", "time",
    ),
    "session_id": (
        "session_id", "session", "sess",
    ),
    "subject_id": (
        "subject_id", "subject", "participant", "participant_id",
        "id", "subj",
    ),
    "room_type": (
        "room_type", "condition", "type", "room_name", "room_condition",
    ),
    "room_number": (
        "room_number", "roomnumber", "room_num", "room", "order", "visit",
    ),
    "valence": (
        "valence", "val", "pleasure", "v",
    ),
    "arousal": (
        "arousal", "ar", "activation", "a",
    ),
    "timestamp_unix": (
        "timestamp_unix", "unix_timestamp", "epoch_s", "time_unix",
    ),
    "force": (
        "force", "resp_force", "belt_force",
    ),
}

# Build a reverse index: normalised_alias → list of canonical names
_ALIAS_TO_CANONICAL: dict[str, list[str]] = {}
for _canon, _aliases in COLUMN_ALIASES.items():
    for _alias in _aliases:
        _ALIAS_TO_CANONICAL.setdefault(_alias, []).append(_canon)


# ── Normalisation helpers ────────────────────────────────────────────────

def _normalise(name: str) -> str:
    """Lowercase, strip, and collapse dashes/underscores/spaces."""
    return re.sub(r"[\s_\-]+", "_", name.strip().lower())


# ── Column classification for ZIP preview ────────────────────────────────

# Signature column sets for each file type. A file is classified as a type
# if the header (lowered) contains *all* columns in one of the signatures.

FILE_TYPE_SIGNATURES: dict[str, list[set[str]]] = {
    "emotibit": [
        {"timestamp_ms", "eda_us"},
        {"localtimestamp"},  # native EmotiBit single-channel
    ],
    "polar": [
        {"timestamp_ms", "hr_bpm"},
        {"timestamp_ms", "rr_ms"},
        {"timestamp_ms", "ecg_uv"},
        {"timestamp_ms", "ecg_mv"},
        {"timestamp_ms", "ecg"},
        {"timestamp_ms", "raw_ecg"},
        {"timestamp_ms", "raw_ecg_uv"},
        {"timestamp_ms", "voltage_uv"},
        {"timestamp_ns", "ecg_uv"},
        {"timestamp_ns", "rr_ms"},
        {"utc_epoch_ns"},
    ],
    "markers": [
        {"event_code", "utc_ms"},
    ],
    "order_affect": [
        {"subject_id", "room_type"},
        {"subject_id", "valence", "arousal"},
        {"subject_id", "room_number", "room_type"},
    ],
    "vernier": [
        {"timestamp_unix", "force"},
    ],
}


def classify_columns(columns: Sequence[str]) -> str:
    """Return the detected file type based on header columns.

    Returns one of: ``emotibit``, ``polar``, ``markers``,
    ``order_affect``, ``vernier``, or ``unknown``.
    """
    lowered = {_normalise(c) for c in columns}
    # Also try raw lowered names (no underscore collapse) for things like
    # "LocalTimestamp" → "localtimestamp"
    lowered_raw = {c.strip().lower() for c in columns}
    combined = lowered | lowered_raw

    # Check each file type in priority order
    for ftype, signatures in FILE_TYPE_SIGNATURES.items():
        for sig in signatures:
            if sig.issubset(combined):
                return ftype
    return "unknown"


# ── Suggestion engine ────────────────────────────────────────────────────

def suggest_column_repairs(
    missing: list[str],
    present: list[str],
) -> list[dict]:
    """Suggest column repairs for *missing* columns given *present* columns.

    For each missing column, checks:
    1. **Alias match (high confidence)**: a *present* column is a known alias.
    2. **Normalised match (medium confidence)**: a *present* column matches
       after underscore/dash/case normalisation.

    Returns a list of dicts::

        {"missing": "eda_us", "found": "EDA", "confidence": "high"}
    """
    suggestions: list[dict] = []
    present_norm = {_normalise(p): p for p in present}

    for col in missing:
        col_lower = col.strip().lower()
        col_norm = _normalise(col)

        # 1. Check alias table: find canonical -> alias list that contains
        #    col_lower, then see if any alias appears in the present columns.
        alias_list = COLUMN_ALIASES.get(col_lower, ())
        if not alias_list:
            # col might itself be an alias of something — but we look for
            # col as canonical, so skip this branch if not found.
            alias_list = (col_lower,)

        for alias in alias_list:
            if alias == col_lower:
                continue  # skip self
            alias_norm = _normalise(alias)
            if alias_norm in present_norm:
                suggestions.append({
                    "missing": col,
                    "found": present_norm[alias_norm],
                    "confidence": "high",
                })

        # 2. Check for normalisation matches (case/dash/underscore)
        if col_norm in present_norm and present_norm[col_norm] != col:
            found_name = present_norm[col_norm]
            # Avoid duplicating if already in suggestions
            if not any(
                s["missing"] == col and s["found"] == found_name
                for s in suggestions
            ):
                suggestions.append({
                    "missing": col,
                    "found": found_name,
                    "confidence": "medium",
                })

        # 3. Also scan all present columns to see if *they* are aliases
        #    of the missing canonical column.
        for present_col in present:
            present_lower = present_col.strip().lower()
            present_n = _normalise(present_col)
            # Check if present_lower is a known alias for col_lower
            canonicals = _ALIAS_TO_CANONICAL.get(present_lower, [])
            if col_lower in canonicals:
                if not any(
                    s["missing"] == col and s["found"] == present_col
                    for s in suggestions
                ):
                    suggestions.append({
                        "missing": col,
                        "found": present_col,
                        "confidence": "high",
                    })

    return suggestions
