"""Generate synthetic test data for the Polar-EmotiBit Analyzer.

Creates aligned EmotiBit, Polar, and markers CSVs simulating a 40-minute
session with baseline + 7 rooms. All timestamps are UTC epoch ms.
"""
import csv
import math
import os
import random

# ── Session parameters ──────────────────────────────────────────
SESSION_START_UTC_MS = 1_715_000_000_000  # ~May 2024 epoch ms
SESSION_DURATION_S = 40 * 60  # 40 minutes
EMOTIBIT_SAMPLE_HZ = 15  # ~15 Hz for EDA
POLAR_SAMPLE_HZ = 1  # 1 Hz for HR (beat-level)

# Room schedule: (label, start_offset_s, duration_s)
ROOM_SCHEDULE = [
    ("baseline", 30, 120),      # 30s in, 2 min baseline
    ("room1", 180, 180),        # 3 min in, 3 min room
    ("room2", 390, 180),
    ("room3", 600, 180),
    ("room4", 810, 180),
    ("room5", 1020, 180),
    ("room6", 1230, 180),
    ("room7", 1440, 180),
]

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def _sim_hr(t_s: float, room_idx: int) -> float:
    """Simulate HR that varies by room with some noise."""
    base = 72.0
    # Each room adds a different stress level
    room_offsets = [0, 5, -2, 12, 8, -1, 15, 3, 10]
    offset = room_offsets[room_idx] if room_idx < len(room_offsets) else 0
    noise = random.gauss(0, 2.0)
    # Slow sinusoidal drift
    drift = 3.0 * math.sin(2 * math.pi * t_s / 600.0)
    return max(50.0, min(150.0, base + offset + noise + drift))


def _sim_eda(t_s: float, room_idx: int) -> float:
    """Simulate EDA (skin conductance) that varies by room."""
    base = 2.5
    room_offsets = [0, 0.3, -0.1, 1.2, 0.8, 0.0, 1.5, 0.2, 0.9]
    offset = room_offsets[room_idx] if room_idx < len(room_offsets) else 0
    noise = random.gauss(0, 0.15)
    # Occasional SCR (skin conductance response) spikes
    scr = 0.0
    if random.random() < 0.02:
        scr = random.uniform(0.3, 1.5)
    return max(0.1, base + offset + noise + scr)


def _current_room(t_s: float) -> int:
    """Return room index (0=pre/between, 1=baseline, 2=room1, etc.)."""
    for i, (label, start, dur) in enumerate(ROOM_SCHEDULE):
        if start <= t_s < start + dur:
            return i
    return 0  # between rooms


def generate_emotibit(path: str) -> int:
    """Generate EmotiBit CSV: timestamp_ms, eda_us, acc_x, acc_y, acc_z."""
    n_samples = int(SESSION_DURATION_S * EMOTIBIT_SAMPLE_HZ)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_ms", "eda_us", "acc_x", "acc_y", "acc_z"])
        for i in range(n_samples):
            t_s = i / EMOTIBIT_SAMPLE_HZ
            ts_ms = SESSION_START_UTC_MS + int(t_s * 1000)
            room = _current_room(t_s)
            eda = _sim_eda(t_s, room)
            # Accelerometer: gentle movement + noise
            acc_x = random.gauss(0, 0.05) + 0.02 * math.sin(t_s / 10.0)
            acc_y = random.gauss(0, 0.05)
            acc_z = random.gauss(9.81, 0.05)
            writer.writerow([ts_ms, f"{eda:.3f}", f"{acc_x:.4f}", f"{acc_y:.4f}", f"{acc_z:.4f}"])
    return n_samples


def generate_polar(path: str) -> int:
    """Generate Polar CSV: timestamp_ms, hr_bpm, rr_ms."""
    n_samples = SESSION_DURATION_S * POLAR_SAMPLE_HZ
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_ms", "hr_bpm", "rr_ms"])
        for i in range(n_samples):
            t_s = i / POLAR_SAMPLE_HZ
            ts_ms = SESSION_START_UTC_MS + int(t_s * 1000)
            room = _current_room(t_s)
            hr = _sim_hr(t_s, room)
            rr = 60000.0 / hr + random.gauss(0, 15)
            writer.writerow([ts_ms, f"{hr:.1f}", f"{rr:.1f}"])
    return n_samples


def generate_markers(path: str) -> int:
    """Generate markers CSV: session_id, event_code, utc_ms, note."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["session_id", "event_code", "utc_ms", "note"])
        count = 0

        # Recording start
        writer.writerow(["TEST_001", "recording_start",
                         SESSION_START_UTC_MS, "session begin"])
        count += 1

        # Room onset/offset pairs
        for label, start_s, dur_s in ROOM_SCHEDULE:
            onset_ms = SESSION_START_UTC_MS + int(start_s * 1000)
            offset_ms = SESSION_START_UTC_MS + int((start_s + dur_s) * 1000)
            writer.writerow(["TEST_001", f"{label}_onset", onset_ms, f"entering {label}"])
            writer.writerow(["TEST_001", f"{label}_offset", offset_ms, f"leaving {label}"])
            count += 2

        # Recording end
        writer.writerow(["TEST_001", "recording_end",
                         SESSION_START_UTC_MS + SESSION_DURATION_S * 1000, "session end"])
        count += 1

    return count


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    em_path = os.path.join(OUT_DIR, "test_emotibit.csv")
    pol_path = os.path.join(OUT_DIR, "test_polar.csv")
    mk_path = os.path.join(OUT_DIR, "test_markers.csv")

    n_em = generate_emotibit(em_path)
    n_pol = generate_polar(pol_path)
    n_mk = generate_markers(mk_path)

    print(f"Generated test data in {OUT_DIR}/")
    print(f"  EmotiBit: {em_path} ({n_em} rows, {EMOTIBIT_SAMPLE_HZ} Hz)")
    print(f"  Polar:    {pol_path} ({n_pol} rows, {POLAR_SAMPLE_HZ} Hz)")
    print(f"  Markers:  {mk_path} ({n_mk} markers)")
    print(f"  Session:  {SESSION_DURATION_S}s from {SESSION_START_UTC_MS}")
    print(f"  Rooms:    {', '.join(r[0] for r in ROOM_SCHEDULE)}")
    print()
    print("Upload these files in the Polar-EmotiBit Analyzer UI:")
    print(f"  EmotiBit slot → {em_path}")
    print(f"  Polar slot    → {pol_path}")
    print(f"  Markers slot  → {mk_path}")


if __name__ == "__main__":
    main()
