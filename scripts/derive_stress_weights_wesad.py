#!/usr/bin/env python3
"""Derive stress-composite weights from the WESAD dataset.

Downloads the public WESAD dataset (Schmidt et al., 2018) and fits a
logistic regression to derive empirically-calibrated channel weights for
the Polar-EmotiBit Analyzer's stress composite.

USAGE:
    # 1. Download WESAD from https://uni-siegen.sciebo.de/s/HGdUkoNlW1Ub0Gx
    #    or from the UCI ML Repository. Place the extracted folders
    #    (S2/, S3/, ..., S17/) into a directory.
    #
    # 2. Run this script:
    python scripts/derive_stress_weights_wesad.py --data-dir /path/to/WESAD
    #
    # 3. The script outputs optimal weights and compares them against
    #    the current heuristic weights.

REFERENCE:
    Schmidt, P., Reiss, A., Duerichen, R., Marber, C., & Van Laerhoven, K.
    (2018). Introducing WESAD, a multimodal dataset for wearable stress and
    affect detection. Proc. ICMI, 400-408. doi:10.1145/3242969.3242985

WHAT THIS DOES:
    1. For each of the 15 WESAD subjects (S2-S17, excl S12):
       - Loads the chest-device pkl (ECG at 700 Hz, EDA at 700 Hz, ACC)
       - Extracts 60-second non-overlapping windows
       - For each window, computes the 5 features our pipeline uses:
         a. HR_norm: mean HR normalized to [0,1] via (HR-60)/60
         b. EDA_norm: mean EDA normalized to [0,1] via EDA/20
         c. phasic_norm: mean |diff(EDA)| normalized to [0,1]
         d. HRV_deficit: (1 - RMSSD/80) — inverse vagal protection
         e. RSA_deficit: (1 - RSA_amplitude/30) — inverse respiratory proxy
       - Labels each window as stress (TSST protocol, label=2) or
         baseline (label=1)
    2. Pools all labeled windows across subjects
    3. Fits a logistic regression (L2-regularized)
    4. Extracts and normalizes the coefficients as weights
    5. Reports the weights and cross-validated accuracy

NOTE: The WESAD dataset is ~18 GB. This script only needs the chest-device
      data (pkl files). If the full dataset is not available, the script
      can also run on a pre-extracted feature CSV (see --features-csv flag).
"""

from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def extract_features_from_subject(
    subject_dir: Path,
    window_s: float = 60.0,
) -> pd.DataFrame:
    """Extract 5-channel stress features from one WESAD subject."""
    pkl_path = subject_dir / f"{subject_dir.name}.pkl"
    if not pkl_path.exists():
        print(f"  SKIP {subject_dir.name}: no pkl file")
        return pd.DataFrame()

    with open(pkl_path, "rb") as f:
        data = pickle.load(f, encoding="latin1")

    # Labels: 0=undefined, 1=baseline, 2=stress, 3=amusement, 4=meditation
    labels = data["label"].flatten()

    # Chest signals
    chest = data["signal"]["chest"]
    ecg = chest["ECG"].flatten()       # 700 Hz
    eda = chest["EDA"].flatten()       # 700 Hz
    # acc = chest["ACC"]               # 700 Hz, 3-axis

    ecg_hz = 700.0
    eda_hz = 700.0
    label_hz = 700.0  # labels are sampled at 700 Hz

    window_samples = int(window_s * ecg_hz)
    n_windows = len(ecg) // window_samples

    rows = []
    for wi in range(n_windows):
        s = wi * window_samples
        e = s + window_samples

        # Majority label for this window
        win_labels = labels[s:e]
        unique, counts = np.unique(win_labels, return_counts=True)
        majority_label = int(unique[np.argmax(counts)])

        # Only keep baseline (1) and stress (2) windows
        if majority_label not in (1, 2):
            continue

        # --- ECG -> HR and HRV ---
        ecg_win = ecg[s:e]
        # Simple R-peak detection via threshold on derivative
        ecg_diff = np.diff(ecg_win)
        threshold = np.std(ecg_diff) * 2.5
        peaks = []
        refractory = int(0.3 * ecg_hz)  # 300ms refractory
        last_peak = -refractory
        for i in range(1, len(ecg_diff) - 1):
            if ecg_diff[i] > threshold and ecg_diff[i] > ecg_diff[i-1] and ecg_diff[i] > ecg_diff[i+1]:
                if i - last_peak > refractory:
                    peaks.append(i)
                    last_peak = i

        if len(peaks) < 5:
            continue

        rr_ms = np.diff(peaks) / ecg_hz * 1000.0
        # Filter ectopic
        median_rr = np.median(rr_ms)
        rr_clean = rr_ms[np.abs(rr_ms - median_rr) / median_rr < 0.30]
        if len(rr_clean) < 3:
            continue

        mean_hr = 60000.0 / np.mean(rr_clean)
        rmssd = float(np.sqrt(np.mean(np.diff(rr_clean) ** 2)))

        # --- EDA ---
        eda_win = eda[s:e]
        mean_eda = float(np.mean(eda_win))
        phasic = float(np.mean(np.abs(np.diff(eda_win))))

        # --- RSA amplitude from RR intervals ---
        rsa_amplitude = 0.0
        if len(rr_clean) >= 10:
            try:
                from scipy.signal import butter, filtfilt, find_peaks as sp_peaks
                # Interpolate RR to uniform 4 Hz
                t_rr = np.cumsum(rr_clean) / 1000.0
                t_uniform = np.arange(t_rr[0], t_rr[-1], 0.25)
                rr_interp = np.interp(t_uniform, t_rr, rr_clean)
                # Bandpass 0.15-0.40 Hz
                nyq = 2.0
                b, a = butter(4, [0.15 / nyq, 0.4 / nyq], btype="band")
                edr = filtfilt(b, a, rr_interp)
                breath_peaks, _ = sp_peaks(edr, distance=8)  # max 30 breaths/min at 4 Hz
                if len(breath_peaks) >= 2:
                    rsa_amplitude = float(np.mean(np.abs(edr[breath_peaks])))
            except Exception:
                pass

        # --- Normalize to our pipeline's scale ---
        hr_norm = max(0.0, min(1.0, (mean_hr - 60.0) / 60.0))
        eda_norm = max(0.0, min(1.0, mean_eda / 20.0))
        phasic_norm = max(0.0, min(1.0, phasic / 2.5))
        hrv_deficit = 1.0 - min(rmssd, 80.0) / 80.0
        rsa_deficit = 1.0 - min(rsa_amplitude, 30.0) / 30.0

        rows.append({
            "subject": subject_dir.name,
            "window": wi,
            "label": majority_label,  # 1=baseline, 2=stress
            "is_stress": int(majority_label == 2),
            "hr_norm": hr_norm,
            "eda_norm": eda_norm,
            "phasic_norm": phasic_norm,
            "hrv_deficit": hrv_deficit,
            "rsa_deficit": rsa_deficit,
            "mean_hr": mean_hr,
            "mean_eda": mean_eda,
            "rmssd": rmssd,
            "rsa_amplitude": rsa_amplitude,
        })

    return pd.DataFrame(rows)


def derive_weights(df: pd.DataFrame) -> dict:
    """Fit logistic regression and extract normalized weights."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import StandardScaler

    feature_cols = ["hr_norm", "eda_norm", "phasic_norm", "hrv_deficit", "rsa_deficit"]
    X = df[feature_cols].values
    y = df["is_stress"].values

    # Standardize for coefficient comparison
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Fit logistic regression
    model = LogisticRegression(C=1.0, penalty="l2", max_iter=1000, random_state=42)
    model.fit(X_scaled, y)

    # Cross-validated accuracy (leave-one-subject-out)
    subjects = df["subject"].values
    unique_subjects = np.unique(subjects)
    from sklearn.model_selection import LeaveOneGroupOut
    logo = LeaveOneGroupOut()
    cv_scores = cross_val_score(model, X_scaled, y, cv=logo, groups=subjects)

    # Extract weights (absolute coefficients, normalized to sum to 1)
    abs_coefs = np.abs(model.coef_[0])
    weights = abs_coefs / abs_coefs.sum()

    channel_names = ["HR", "EDA_tonic", "EDA_phasic", "HRV_deficit", "RSA_deficit"]
    result = {
        "weights": {name: round(float(w), 4) for name, w in zip(channel_names, weights)},
        "raw_coefficients": {name: round(float(c), 4) for name, c in zip(channel_names, model.coef_[0])},
        "intercept": round(float(model.intercept_[0]), 4),
        "accuracy_mean": round(float(np.mean(cv_scores)), 4),
        "accuracy_std": round(float(np.std(cv_scores)), 4),
        "n_subjects": len(unique_subjects),
        "n_baseline_windows": int((y == 0).sum()),
        "n_stress_windows": int((y == 1).sum()),
    }
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Derive stress-composite weights from WESAD dataset"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Path to WESAD directory containing S2/, S3/, ... subdirectories",
    )
    parser.add_argument(
        "--features-csv",
        type=Path,
        help="Pre-extracted features CSV (skip raw extraction)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("scripts/wesad_derived_weights.json"),
        help="Output JSON file for derived weights",
    )
    args = parser.parse_args()

    if args.features_csv and args.features_csv.exists():
        print(f"Loading pre-extracted features from {args.features_csv}")
        df = pd.read_csv(args.features_csv)
    elif args.data_dir and args.data_dir.exists():
        print(f"Extracting features from WESAD data in {args.data_dir}")
        subject_dirs = sorted([
            d for d in args.data_dir.iterdir()
            if d.is_dir() and d.name.startswith("S") and d.name != "S12"
        ])
        print(f"  Found {len(subject_dirs)} subjects: {[d.name for d in subject_dirs]}")

        frames = []
        for sd in subject_dirs:
            print(f"  Processing {sd.name}...")
            sdf = extract_features_from_subject(sd)
            if not sdf.empty:
                frames.append(sdf)
                print(f"    → {len(sdf)} windows ({sdf['is_stress'].sum()} stress, {(~sdf['is_stress'].astype(bool)).sum()} baseline)")

        if not frames:
            print("ERROR: No features extracted. Check data directory.")
            sys.exit(1)

        df = pd.concat(frames, ignore_index=True)

        # Save extracted features for reuse
        features_path = args.data_dir / "extracted_features.csv"
        df.to_csv(features_path, index=False)
        print(f"\nExtracted features saved to {features_path}")
    else:
        print("ERROR: Provide either --data-dir or --features-csv")
        print("\nTo download WESAD:")
        print("  https://uni-siegen.sciebo.de/s/HGdUkoNlW1Ub0Gx")
        print("  or: https://archive.ics.uci.edu/dataset/465/wesad")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Total windows: {len(df)} ({df['is_stress'].sum()} stress, {(~df['is_stress'].astype(bool)).sum()} baseline)")
    print(f"Subjects: {sorted(df['subject'].unique().tolist())}")

    # Derive weights
    print(f"\nFitting logistic regression...")
    result = derive_weights(df)

    print(f"\n{'='*60}")
    print(f"DERIVED WEIGHTS (from WESAD, {result['n_subjects']} subjects)")
    print(f"{'='*60}")
    for name, w in result["weights"].items():
        print(f"  {name:<14s}: {w:.4f}")
    print(f"\n  Leave-one-subject-out accuracy: {result['accuracy_mean']:.4f} ± {result['accuracy_std']:.4f}")

    print(f"\nCurrent heuristic weights (V2.2, 5-channel):")
    current = {"HR": 0.25, "EDA_tonic": 0.25, "EDA_phasic": 0.15, "HRV_deficit": 0.15, "RSA_deficit": 0.20}
    for name, w in current.items():
        derived = result["weights"].get(name, 0)
        delta = derived - w
        print(f"  {name:<14s}: {w:.4f} → {derived:.4f}  (Δ={delta:+.4f})")

    # Save to JSON
    import json
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
