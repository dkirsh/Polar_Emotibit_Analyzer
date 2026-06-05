from __future__ import annotations

from app.services.processing.group_statistics import build_condition_aggregate_inference


def test_group_inference_detects_visit_effect_but_not_condition_effect_in_constructed_rows():
    rows = []
    conditions = ["A", "B", "C", "D"]
    for subject_idx in range(1, 9):
        subject = f"p{subject_idx:03d}"
        shift = (subject_idx - 1) % 4
        mapping = conditions[shift:] + conditions[:shift]
        for visit_number, room_type in enumerate(mapping, start=1):
            rows.append(
                {
                    "subject_id": subject,
                    "room_type": room_type,
                    "visit_number": visit_number,
                    # strong visit effect, no stable condition effect
                    "mean_hr_delta_bpm": float(visit_number * 2),
                    "mean_hr_pct_change": float(visit_number * 3),
                    "mean_eda_delta_us": float(visit_number * 0.5),
                    "eda_phasic_delta": float(0.01 if visit_number == 1 else 0.0),
                    "ln_rmssd_delta": float(-0.1 * visit_number),
                }
            )

    inf = build_condition_aggregate_inference(rows)
    hr = next(metric for metric in inf["normalized_metrics"] if metric["key"] == "mean_hr_delta_bpm")
    assert hr["visit_friedman"] is not None
    assert hr["condition_friedman"] is not None
    assert hr["visit_friedman"]["p"] < 0.05
    assert hr["blocked_model"]["visit_given_subject"]["p"] < 0.05
    assert hr["blocked_model"]["condition_given_subject_and_visit"]["p"] > 0.05
