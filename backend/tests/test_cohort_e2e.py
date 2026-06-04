"""End-to-end cohort test on Alice p012–p044.

Unzips the four Alice archives to a temp directory, runs the full analysis
pipeline for each subject (p012 through p044, except p026 — no physiology),
and verifies that each subject produces valid HRV, EDA, and room-level
features.

Marked @pytest.mark.slow so it is excluded from the fast CI suite:
    pytest -m "not slow"    # skip this
    pytest -m slow          # run only this
"""

from __future__ import annotations

import csv
import io
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

# ── Imports from the backend app ─────────────────────────────────────────
from app.services.ingestion.parsers import parse_emotibit_csv, parse_polar_csv
from app.services.processing.pipeline import InsufficientDataError, run_analysis

# ── Constants ────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
ALICE_DIR = REPO_ROOT / "data" / "Alice"

EMOTIBIT_ZIP = ALICE_DIR / "emotibit_for_david_p012-044.zip"
POLAR_ZIP = ALICE_DIR / "polar_for_david_p012-044.zip"
MARKERS_ZIP = ALICE_DIR / "event_markers_p012-044.zip"
ORDER_AFFECT_ZIP = ALICE_DIR / "order_affect_for_david_p012-044.zip"

# p026 is documented as missing physiology data.
EXPECTED_MISSING = {"p026"}

# Naming conventions from the ZIP description doc:
#   emotibit: p0XX_emotibit_for_david.csv
#   polar:    p0XX_polar_for_david.csv
#   markers:  p0XX_event_markers_for_david_25s.csv
#   order:    p0XX_order_affect_for_david.csv
_SUBJECT_RE = re.compile(r"p(\d{3})")


# ── Helpers ──────────────────────────────────────────────────────────────

def _csv_texts_by_subject(zip_path: Path) -> dict[str, str]:
    """Read all per-subject CSVs from a ZIP, keyed by normalised subject id."""
    out: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            basename = info.filename.split("/")[-1]
            if not basename.lower().endswith(".csv") or basename.startswith((".","__")):
                continue
            match = _SUBJECT_RE.search(basename.lower())
            if match is None:
                continue
            subject = f"p{match.group(1)}"
            out[subject] = zf.read(info.filename).decode("utf-8", errors="replace")
    return out


def _parse_markers(text: str) -> list[dict[str, Any]]:
    """Parse an event-markers CSV into a list of dicts."""
    df = pd.read_csv(io.StringIO(text))
    markers: list[dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        try:
            markers.append({
                "event_code": str(row.get("event_code", "")),
                "utc_ms": int(row.get("utc_ms")),
                "note": str(row.get("note", "")) if "note" in row and pd.notna(row.get("note")) else "",
            })
        except (TypeError, ValueError):
            continue
    return markers


def _parse_order_affect(text: str) -> dict[str, Any] | None:
    """Parse an order-affect CSV; return None on failure."""
    try:
        from app.services.ingestion.order_affect import parse_order_affect_csv
        return parse_order_affect_csv(text).to_dict()
    except Exception:
        return None


def _run_subject(
    subject: str,
    em_text: str,
    pol_text: str,
    marker_text: str | None,
    order_text: str | None,
) -> dict[str, Any]:
    """Run the full pipeline for a single subject and return a result dict."""
    result_row: dict[str, Any] = {
        "subject": subject,
        "status": "unknown",
        "error": None,
        # HRV
        "rmssd_ms": None,
        "sdnn_ms": None,
        "mean_hr_bpm": None,
        "rr_source": None,
        "nn50": None,
        "pnn50": None,
        # EDA
        "eda_mean_us": None,
        "eda_phasic_index": None,
        # Sync
        "synchronized_samples": None,
        "sync_qc_score": None,
        "sync_qc_gate": None,
        # Stress
        "stress_v1": None,
        "stress_v2": None,
        # Room stats
        "n_rooms": None,
        "has_order_affect": order_text is not None,
        "has_markers": marker_text is not None,
    }

    try:
        em_df = parse_emotibit_csv(em_text)
        pol_df = parse_polar_csv(pol_text)
        analysis = run_analysis(em_df, pol_df)
    except InsufficientDataError as exc:
        result_row["status"] = "insufficient_data"
        result_row["error"] = str(exc)
        return result_row
    except Exception as exc:
        result_row["status"] = "failed"
        result_row["error"] = f"{exc.__class__.__name__}: {exc}"
        return result_row

    fs = analysis.feature_summary
    result_row.update({
        "status": "ok",
        "rmssd_ms": fs.rmssd_ms,
        "sdnn_ms": fs.sdnn_ms,
        "mean_hr_bpm": fs.mean_hr_bpm,
        "rr_source": fs.rr_source,
        "nn50": fs.nn50,
        "pnn50": fs.pnn50,
        "eda_mean_us": fs.eda_mean_us,
        "eda_phasic_index": fs.eda_phasic_index,
        "synchronized_samples": analysis.synchronized_samples,
        "sync_qc_score": analysis.sync_qc_score,
        "sync_qc_gate": analysis.sync_qc_gate,
        "stress_v1": fs.stress_score,
        "stress_v2": fs.stress_score_v2,
    })

    # Room-level stats (optional)
    if marker_text is not None:
        try:
            from app.services.processing.room_analysis import compute_room_stats
            from app.services.processing.drift import estimate_piecewise_drift, apply_piecewise_drift
            from app.services.processing.sync import synchronize_signals
            from app.services.processing.clean import clean_signals

            markers = _parse_markers(marker_text)
            oa_data = _parse_order_affect(order_text) if order_text else None

            drift_model = estimate_piecewise_drift(
                source_ts=pol_df["timestamp_ms"].astype(int).tolist(),
                reference_ts=em_df["timestamp_ms"].astype(int).tolist(),
            )
            corrected = pol_df.copy()
            corrected["timestamp_ms"] = apply_piecewise_drift(
                corrected["timestamp_ms"].astype(int).tolist(), drift_model,
            )
            synced = synchronize_signals(em_df, corrected)
            cleaned, _ = clean_signals(synced)
            room_stats = compute_room_stats(cleaned, markers, oa_data)
            room_entries = [r for r in room_stats if str(r.get("room_key", "")).lower().startswith("room")]
            result_row["n_rooms"] = len(room_entries)
        except Exception as exc:
            result_row["n_rooms"] = 0
            result_row["error"] = f"room_stats: {exc.__class__.__name__}: {exc}"

    return result_row


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def alice_data() -> dict[str, dict[str, str]]:
    """Load all four Alice ZIPs into per-subject text dicts.

    Returns a dict with keys 'emotibit', 'polar', 'markers', 'order_affect',
    each mapping subject -> csv text.
    """
    for zp in (EMOTIBIT_ZIP, POLAR_ZIP, MARKERS_ZIP, ORDER_AFFECT_ZIP):
        if not zp.exists():
            pytest.skip(f"Alice data not available: {zp.name}")

    return {
        "emotibit": _csv_texts_by_subject(EMOTIBIT_ZIP),
        "polar": _csv_texts_by_subject(POLAR_ZIP),
        "markers": _csv_texts_by_subject(MARKERS_ZIP),
        "order_affect": _csv_texts_by_subject(ORDER_AFFECT_ZIP),
    }


@pytest.fixture(scope="module")
def subjects(alice_data: dict[str, dict[str, str]]) -> list[str]:
    """All subjects present in both emotibit and polar ZIPs."""
    em_subs = set(alice_data["emotibit"])
    pol_subs = set(alice_data["polar"])
    return sorted(em_subs & pol_subs)


@pytest.fixture(scope="module")
def cohort_results(
    alice_data: dict[str, dict[str, str]],
    subjects: list[str],
) -> list[dict[str, Any]]:
    """Run the full pipeline for every subject and collect results."""
    results: list[dict[str, Any]] = []
    for subj in subjects:
        row = _run_subject(
            subj,
            em_text=alice_data["emotibit"][subj],
            pol_text=alice_data["polar"][subj],
            marker_text=alice_data["markers"].get(subj),
            order_text=alice_data["order_affect"].get(subj),
        )
        results.append(row)
    return results


@pytest.fixture(scope="module")
def comparison_csv(
    cohort_results: list[dict[str, Any]],
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    """Write a cross-subject comparison CSV and return its path."""
    out_dir = tmp_path_factory.mktemp("cohort_output")
    csv_path = out_dir / "alice_cohort_comparison.csv"

    if not cohort_results:
        csv_path.write_text("subject,status,error\n")
        return csv_path

    fieldnames = list(cohort_results[0].keys())
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cohort_results)
    return csv_path


# ── Tests ────────────────────────────────────────────────────────────────

@pytest.mark.slow
class TestAliceCohortE2E:
    """End-to-end cohort test on Alice p012–p044."""

    def test_all_expected_subjects_present(
        self, subjects: list[str], alice_data: dict[str, dict[str, str]]
    ) -> None:
        """Both ZIPs should contain the same subject set (minus p026)."""
        for subj in subjects:
            assert subj not in EXPECTED_MISSING, f"{subj} should not be in the physiology ZIPs"
        # We expect at least 30 subjects (32 total minus p026 = 31)
        assert len(subjects) >= 30, f"Expected ≥30 subjects, got {len(subjects)}"

    def test_no_unhandled_exceptions(self, cohort_results: list[dict[str, Any]]) -> None:
        """No subject should crash the pipeline with an unhandled exception."""
        crashed = [r for r in cohort_results if r["status"] == "failed"]
        if crashed:
            details = "\n".join(f"  {r['subject']}: {r['error']}" for r in crashed)
            pytest.fail(f"{len(crashed)} subject(s) crashed:\n{details}")

    def test_majority_succeed(self, cohort_results: list[dict[str, Any]]) -> None:
        """At least 80% of subjects should succeed (some may have data issues)."""
        ok = [r for r in cohort_results if r["status"] == "ok"]
        total = len(cohort_results)
        ratio = len(ok) / total if total > 0 else 0
        assert ratio >= 0.80, (
            f"Only {len(ok)}/{total} ({ratio:.0%}) succeeded; "
            f"expected ≥80%"
        )

    def test_valid_hrv_features(self, cohort_results: list[dict[str, Any]]) -> None:
        """Every successful subject should have physiologically plausible HRV."""
        for r in cohort_results:
            if r["status"] != "ok":
                continue
            subj = r["subject"]
            assert r["rmssd_ms"] is not None and r["rmssd_ms"] > 0, (
                f"{subj}: RMSSD should be positive, got {r['rmssd_ms']}"
            )
            assert r["sdnn_ms"] is not None and r["sdnn_ms"] > 0, (
                f"{subj}: SDNN should be positive, got {r['sdnn_ms']}"
            )
            assert r["mean_hr_bpm"] is not None, f"{subj}: mean HR missing"
            assert 30 <= r["mean_hr_bpm"] <= 220, (
                f"{subj}: mean HR {r['mean_hr_bpm']} outside 30–220 bpm"
            )
            assert r["rr_source"] in ("native_polar", "derived_from_bpm", "derived_from_ecg"), (
                f"{subj}: unexpected rr_source {r['rr_source']!r}"
            )

    def test_valid_eda_features(self, cohort_results: list[dict[str, Any]]) -> None:
        """Every successful subject should have valid EDA features."""
        for r in cohort_results:
            if r["status"] != "ok":
                continue
            subj = r["subject"]
            assert r["eda_mean_us"] is not None, f"{subj}: EDA mean missing"
            # EDA can be near-zero but should not be negative
            assert r["eda_mean_us"] >= 0, (
                f"{subj}: EDA mean {r['eda_mean_us']} should be ≥0"
            )
            assert r["eda_phasic_index"] is not None, f"{subj}: EDA phasic index missing"
            assert r["eda_phasic_index"] >= 0, (
                f"{subj}: EDA phasic index {r['eda_phasic_index']} should be ≥0"
            )

    def test_room_stats_when_markers_present(self, cohort_results: list[dict[str, Any]]) -> None:
        """Most subjects with markers + order-affect should have room-level stats.

        Some subjects (e.g. p034 early stop, or marker/data misalignment)
        may legitimately have 0 rooms. We require ≥80% of eligible subjects
        to produce at least 1 room stat.
        """
        eligible = [
            r for r in cohort_results
            if r["status"] == "ok" and r["has_markers"] and r["has_order_affect"]
        ]
        with_rooms = [r for r in eligible if (r.get("n_rooms") or 0) >= 1]
        without_rooms = [r for r in eligible if (r.get("n_rooms") or 0) == 0]
        ratio = len(with_rooms) / len(eligible) if eligible else 0
        assert ratio >= 0.80, (
            f"Only {len(with_rooms)}/{len(eligible)} ({ratio:.0%}) subjects "
            f"with markers+O&A produced room stats; expected ≥80%. "
            f"Missing: {[r['subject'] for r in without_rooms]}"
        )

    def test_comparison_csv_generated(self, comparison_csv: Path) -> None:
        """A cross-subject comparison CSV should exist and be parseable."""
        assert comparison_csv.exists(), "Comparison CSV was not generated"
        df = pd.read_csv(comparison_csv)
        assert len(df) > 0, "Comparison CSV is empty"
        required_cols = {"subject", "status", "rmssd_ms", "sdnn_ms", "mean_hr_bpm",
                         "eda_mean_us", "eda_phasic_index"}
        assert required_cols.issubset(set(df.columns)), (
            f"Missing columns in CSV: {required_cols - set(df.columns)}"
        )

    def test_summary_report(
        self,
        cohort_results: list[dict[str, Any]],
        comparison_csv: Path,
    ) -> None:
        """Print a human-readable summary of the cohort run."""
        ok = [r for r in cohort_results if r["status"] == "ok"]
        failed = [r for r in cohort_results if r["status"] == "failed"]
        insufficient = [r for r in cohort_results if r["status"] == "insufficient_data"]
        total = len(cohort_results)

        lines = [
            "",
            "=" * 60,
            f"ALICE COHORT SUMMARY: {len(ok)}/{total} succeeded",
            f"  OK:               {len(ok)}",
            f"  Insufficient:     {len(insufficient)}",
            f"  Failed:           {len(failed)}",
            f"  Comparison CSV:   {comparison_csv}",
            "=" * 60,
        ]
        if failed:
            lines.append("FAILURES:")
            for r in failed:
                lines.append(f"  {r['subject']}: {r['error']}")
        if insufficient:
            lines.append("INSUFFICIENT DATA:")
            for r in insufficient:
                lines.append(f"  {r['subject']}: {r['error']}")

        # Print to stdout so pytest -s shows it
        print("\n".join(lines))

        # The test itself just asserts the summary could be built
        assert total > 0
