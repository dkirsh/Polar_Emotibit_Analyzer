"""Tests for within-subject normalization (the user's 'difference from each
subject's own mean' method). Severity-oriented: the centred values must sum to
~0 and be invariant to a subject's additive level offset; a non-finite sample
must not shift the centre."""
from __future__ import annotations

import numpy as np

from app.services.processing.normalization import (
    within_subject_center,
    within_subject_condition_means,
)


def test_centering_removes_subject_level_offset():
    base = [10.0, 12.0, 8.0, 14.0, 6.0]
    a = within_subject_center(base)
    # Same shape shifted up by 100 → identical centred values (level offset gone)
    b = within_subject_center([x + 100 for x in base])
    assert a["centered"] == b["centered"]
    assert abs(sum(v for v in a["centered"] if v is not None)) < 1e-6
    assert a["subject_mean"] == 10.0


def test_standardize_unit_sd():
    z = within_subject_center([1, 2, 3, 4, 5], standardize=True)["z"]
    zz = np.array([v for v in z if v is not None])
    assert abs(zz.mean()) < 1e-6
    assert abs(zz.std(ddof=0) - 1.0) < 0.2  # ddof difference tolerance


def test_nonfinite_sample_does_not_shift_centre():
    clean = within_subject_center([4.0, 6.0])
    withbad = within_subject_center([4.0, 6.0, float("inf"), float("nan")])
    assert withbad["subject_mean"] == clean["subject_mean"] == 5.0
    # bad samples pass through as None, not as a shifted number
    assert withbad["centered"][2] is None and withbad["centered"][3] is None


def test_condition_means_relative_to_own_grand_mean():
    # One subject, two conditions; plant lower than no_plant on the measure.
    rows = [
        {"condition": "plants", "eda": 2.0},
        {"condition": "plants", "eda": 4.0},
        {"condition": "no_plants", "eda": 8.0},
        {"condition": "no_plants", "eda": 10.0},
    ]
    res = within_subject_condition_means(rows, "eda")
    assert res["subject_mean"] == 6.0
    assert res["conditions"]["plants"]["centered_mean"] == -3.0   # mean 3 − 6
    assert res["conditions"]["no_plants"]["centered_mean"] == 3.0  # mean 9 − 6
