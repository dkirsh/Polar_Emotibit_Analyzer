"""Order & Affect CSV parser.

Parses the room-visit-order and self-report affect file that experimenters
provide. This maps each subject's room visit sequence to room types and
attaches valence/arousal self-report ratings.

Expected CSV schema (one row per room per subject):
    subject_id, room_number, room_type, valence, arousal

Example:
    subject_id,room_number,room_type,valence,arousal
    P041,1,A,3.5,2.1
    P041,2,B,4.2,1.8
    ...
    P041,8,H,2.9,3.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
from typing import Any

import pandas as pd


@dataclass
class RoomAssignment:
    """One room visit for one subject."""
    room_number: int
    room_type: str
    valence: float | None
    arousal: float | None


@dataclass
class OrderAffectData:
    """Parsed Order & Affect file for a single subject."""
    subject_id: str
    rooms: list[RoomAssignment] = field(default_factory=list)
    n_rooms: int = 0

    def room_type_for(self, room_number: int) -> str | None:
        """Look up the room type for a given visit number."""
        for r in self.rooms:
            if r.room_number == room_number:
                return r.room_type
        return None

    def room_type_map(self) -> dict[int, str]:
        """Return {room_number: room_type} mapping."""
        return {r.room_number: r.room_type for r in self.rooms}

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON storage in the session store."""
        return {
            "subject_id": self.subject_id,
            "n_rooms": self.n_rooms,
            "rooms": [
                {
                    "room_number": r.room_number,
                    "room_type": r.room_type,
                    "valence": r.valence,
                    "arousal": r.arousal,
                }
                for r in self.rooms
            ],
        }


# Flexible column name mapping for resilience to minor header variations
_SUBJECT_ID_CANDIDATES = ("subject_id", "subjectid", "subject", "participant", "id")
_ROOM_NUMBER_CANDIDATES = ("room_number", "roomnumber", "room_num", "room", "order", "visit")
_ROOM_TYPE_CANDIDATES = ("room_type", "roomtype", "type", "condition", "room_name")
_VALENCE_CANDIDATES = ("valence", "val", "pleasure", "v")
_AROUSAL_CANDIDATES = ("arousal", "ar", "activation", "a")


def _find_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    """Find the first matching column name (case-insensitive)."""
    col_lower = {c.lower().strip(): c for c in columns}
    for candidate in candidates:
        if candidate in col_lower:
            return col_lower[candidate]
    return None


def parse_order_affect_csv(csv_text: str) -> OrderAffectData:
    """Parse an Order & Affect CSV file.

    Args:
        csv_text: raw CSV text.

    Returns:
        OrderAffectData with parsed room assignments.

    Raises:
        ValueError: if required columns are missing or data is malformed.
    """
    df = pd.read_csv(StringIO(csv_text))

    # Find columns
    subject_col = _find_column(list(df.columns), _SUBJECT_ID_CANDIDATES)
    room_num_col = _find_column(list(df.columns), _ROOM_NUMBER_CANDIDATES)
    room_type_col = _find_column(list(df.columns), _ROOM_TYPE_CANDIDATES)
    valence_col = _find_column(list(df.columns), _VALENCE_CANDIDATES)
    arousal_col = _find_column(list(df.columns), _AROUSAL_CANDIDATES)

    if subject_col is None:
        raise ValueError(
            f"Order & Affect file missing subject ID column. "
            f"Expected one of: {list(_SUBJECT_ID_CANDIDATES)}. "
            f"Got: {list(df.columns)}"
        )
    if room_type_col is None and room_num_col is None:
        raise ValueError(
            f"Order & Affect file missing room columns. "
            f"Expected 'room_number' + 'room_type' or at least one of them. "
            f"Got: {list(df.columns)}"
        )

    # Extract subject_id from the first row
    subject_id = str(df[subject_col].iloc[0]).strip()

    rooms: list[RoomAssignment] = []
    for i, row in df.iterrows():
        room_number = int(row[room_num_col]) if room_num_col else i + 1
        room_type = str(row[room_type_col]).strip() if room_type_col else str(room_number)

        valence = None
        if valence_col and pd.notna(row.get(valence_col)):
            try:
                valence = float(row[valence_col])
            except (ValueError, TypeError):
                pass

        arousal = None
        if arousal_col and pd.notna(row.get(arousal_col)):
            try:
                arousal = float(row[arousal_col])
            except (ValueError, TypeError):
                pass

        rooms.append(RoomAssignment(
            room_number=room_number,
            room_type=room_type,
            valence=valence,
            arousal=arousal,
        ))

    return OrderAffectData(
        subject_id=subject_id,
        rooms=rooms,
        n_rooms=len(rooms),
    )


def validate_order_affect_csv(csv_text: str) -> dict[str, Any]:
    """Validate and return summary info for the frontend validation endpoint."""
    data = parse_order_affect_csv(csv_text)
    valences = [r.valence for r in data.rooms if r.valence is not None]
    arousals = [r.arousal for r in data.rooms if r.arousal is not None]
    room_types = [r.room_type for r in data.rooms]
    return {
        "valid": True,
        "subject_id": data.subject_id,
        "n_rooms": data.n_rooms,
        "room_types": room_types,
        "valence_range": {
            "min": min(valences) if valences else None,
            "max": max(valences) if valences else None,
        },
        "arousal_range": {
            "min": min(arousals) if arousals else None,
            "max": max(arousals) if arousals else None,
        },
    }
