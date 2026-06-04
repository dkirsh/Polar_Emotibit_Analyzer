"""Tests for the Vernier respiration-belt parser.

Covers:
  - Happy-path parsing and respiratory feature extraction
  - Empty file rejection
  - Missing columns
  - NaN-heavy force column
  - Zero-length recording
  - Mixed-frequency resampling to 20 Hz
  - Validation endpoint round-trip
"""

from __future__ import annotations

import io
from typing import Any

import numpy as np
import pandas as pd
import pytest

from app.services.ingestion.vernier_parser import (
    REQUIRED_VERNIER_COLUMNS,
    VERNIER_SAMPLE_RATE_HZ,
    VernierParseResult,
    compute_respiratory_features,
    parse_and_analyze_vernier,
    parse_vernier_xlsx,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_xlsx(df: pd.DataFrame) -> bytes:
    """Write a DataFrame to .xlsx bytes."""
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _sine_vernier_df(
    n_seconds: float = 30.0,
    rate_hz: float = 50.0,
    breath_freq: float = 0.25,  # 15 bpm
    noise_std: float = 0.01,
) -> pd.DataFrame:
    """Generate a synthetic Vernier respiration-belt DataFrame.

    Produces a sinusoidal force signal at a given sampling rate with
    timestamps, event markers, and condition labels.
    """
    n = int(n_seconds * rate_hz)
    t_unix = np.linspace(1700000000.0, 1700000000.0 + n_seconds, n)
    elapsed = t_unix - t_unix[0]
    force = np.sin(2 * np.pi * breath_freq * elapsed)
    rng = np.random.default_rng(42)
    force += rng.normal(0, noise_std, n)

    rr = np.full(n, 60.0 * breath_freq)  # vendor-computed RR
    event_marker = ["baseline"] * (n // 3) + ["stress"] * (n // 3) + ["recovery"] * (n - 2 * (n // 3))
    condition = ["neutral"] * (n // 2) + ["active"] * (n - n // 2)

    return pd.DataFrame({
        "timestamp": pd.date_range("2023-11-15 10:00:00", periods=n, freq=f"{int(1e9 / rate_hz)}ns"),
        "timestamp_unix": t_unix,
        "force": force,
        "RR": rr,
        "event_marker": event_marker,
        "condition": condition,
    })


# ── Tests: parse_vernier_xlsx ────────────────────────────────────────────────


class TestParseVernierXlsx:
    """Core parser tests."""

    def test_happy_path(self) -> None:
        """A well-formed file parses correctly."""
        df = _sine_vernier_df(n_seconds=30.0, rate_hz=50.0)
        raw = _make_xlsx(df)
        result = parse_vernier_xlsx(raw)

        assert isinstance(result, VernierParseResult)
        assert len(result.timeseries) > 0
        assert "timestamp_ms" in result.timeseries.columns
        assert "force" in result.timeseries.columns
        assert result.metadata["source_type"] == "vernier_respiration_belt"
        assert result.metadata["sample_rate_hz"] == VERNIER_SAMPLE_RATE_HZ
        assert result.metadata["duration_s"] > 0
        assert result.metadata["n_raw_samples"] == len(df)

    def test_resampled_to_20hz(self) -> None:
        """Output is uniformly sampled at 20 Hz regardless of input rate."""
        df = _sine_vernier_df(n_seconds=10.0, rate_hz=100.0)
        result = parse_vernier_xlsx(_make_xlsx(df))

        expected_n = int(10.0 * VERNIER_SAMPLE_RATE_HZ)
        assert abs(len(result.timeseries) - expected_n) <= 1  # ±1 for rounding

        # Check uniform spacing
        ts = result.timeseries["timestamp_ms"].values
        diffs = np.diff(ts)
        assert np.all(diffs == 50)  # 1000 ms / 20 Hz = 50 ms

    def test_event_markers_extracted(self) -> None:
        """Event markers with transitions are detected."""
        df = _sine_vernier_df()
        result = parse_vernier_xlsx(_make_xlsx(df))

        assert len(result.event_markers) >= 2  # baseline→stress, stress→recovery
        codes = [m["event_code"] for m in result.event_markers]
        assert "baseline" in codes
        assert "stress" in codes

    def test_conditions_extracted(self) -> None:
        """Conditions from the condition column are listed."""
        df = _sine_vernier_df()
        result = parse_vernier_xlsx(_make_xlsx(df))

        assert "conditions" in result.metadata
        conds = result.metadata["conditions"]
        assert "neutral" in conds
        assert "active" in conds

    def test_vendor_rr_validation(self) -> None:
        """Vendor RR statistics are computed when RR column is present."""
        df = _sine_vernier_df()
        result = parse_vernier_xlsx(_make_xlsx(df))

        rr_val = result.metadata["rr_validation"]
        assert rr_val is not None
        assert rr_val["vendor_rr_median"] > 0

    def test_minimal_columns(self) -> None:
        """Only timestamp_unix and force are required."""
        df = pd.DataFrame({
            "timestamp_unix": np.linspace(0, 30, 100),
            "force": np.sin(np.linspace(0, 6 * np.pi, 100)),
        })
        result = parse_vernier_xlsx(_make_xlsx(df))
        assert result.metadata["n_raw_samples"] == 100
        assert result.metadata["rr_validation"] is None
        assert result.event_markers == []


# ── Adversarial tests ────────────────────────────────────────────────────────


class TestVernierAdversarial:
    """Edge cases and error handling."""

    def test_empty_file(self) -> None:
        """Empty XLSX raises ValueError with a clear message."""
        df = pd.DataFrame({"timestamp_unix": [], "force": []})
        with pytest.raises(ValueError, match="at least 10"):
            parse_vernier_xlsx(_make_xlsx(df))

    def test_missing_columns(self) -> None:
        """Missing required columns produce a specific error."""
        df = pd.DataFrame({"time": [1, 2, 3], "value": [0.1, 0.2, 0.3]})
        with pytest.raises(ValueError, match="missing required columns"):
            parse_vernier_xlsx(_make_xlsx(df))

    def test_missing_force_column(self) -> None:
        """Missing force column is caught."""
        df = pd.DataFrame({
            "timestamp_unix": np.arange(100),
            "voltage": np.random.randn(100),
        })
        with pytest.raises(ValueError, match="force"):
            parse_vernier_xlsx(_make_xlsx(df))

    def test_nan_heavy_force(self) -> None:
        """NaN-heavy force column degrades gracefully."""
        n = 200
        force = np.full(n, np.nan)
        force[50:55] = np.sin(np.linspace(0, np.pi, 5))  # only 5 valid
        df = pd.DataFrame({
            "timestamp_unix": np.linspace(0, 30, n),
            "force": force,
        })
        with pytest.raises(ValueError, match="too few valid"):
            parse_vernier_xlsx(_make_xlsx(df))

    def test_zero_duration_recording(self) -> None:
        """All-same timestamps → zero duration → rejection."""
        n = 50
        df = pd.DataFrame({
            "timestamp_unix": np.full(n, 1700000000.0),
            "force": np.sin(np.linspace(0, 2 * np.pi, n)),
        })
        with pytest.raises(ValueError, match="zero or negative duration"):
            parse_vernier_xlsx(_make_xlsx(df))

    def test_corrupted_xlsx(self) -> None:
        """Non-Excel bytes raise ValueError."""
        with pytest.raises(ValueError, match="Could not read"):
            parse_vernier_xlsx(b"this is not an excel file")

    def test_single_row(self) -> None:
        """Single-row file is rejected."""
        df = pd.DataFrame({"timestamp_unix": [1.0], "force": [0.5]})
        with pytest.raises(ValueError, match="at least 10"):
            parse_vernier_xlsx(_make_xlsx(df))


# ── Tests: compute_respiratory_features ──────────────────────────────────────


class TestRespiratoryFeatures:
    """Respiratory cycle detection and feature extraction."""

    def test_sinusoidal_signal(self) -> None:
        """Clean sine wave produces expected breath rate."""
        fs = VERNIER_SAMPLE_RATE_HZ
        dur = 60.0
        breath_freq = 0.25  # 15 bpm
        t = np.arange(0, dur, 1.0 / fs)
        force = np.sin(2 * np.pi * breath_freq * t) * 5.0

        features = compute_respiratory_features(force, fs=fs)

        assert features["n_breaths"] > 0
        assert features["resp_rate_bpm"] is not None
        # Should be approximately 15 bpm (±3 bpm tolerance)
        assert abs(features["resp_rate_bpm"] - 15.0) < 3.0

    def test_short_signal(self) -> None:
        """Signal < 5 seconds returns error message."""
        features = compute_respiratory_features(np.zeros(50), fs=VERNIER_SAMPLE_RATE_HZ)
        assert features["n_breaths"] == 0
        assert "error" in features

    def test_per_breath_features(self) -> None:
        """Per-breath features are returned with expected keys."""
        fs = VERNIER_SAMPLE_RATE_HZ
        t = np.arange(0, 60, 1.0 / fs)
        force = np.sin(2 * np.pi * 0.2 * t) * 10.0  # 12 bpm

        features = compute_respiratory_features(force, fs=fs)
        assert len(features["per_breath"]) > 0

        breath = features["per_breath"][0]
        assert "inhale_dur_s" in breath
        assert "exhale_dur_s" in breath
        assert "cycle_dur_s" in breath
        assert "ie_ratio" in breath
        assert "duty_cycle" in breath
        assert "amplitude" in breath

    def test_ie_ratio_near_unity_for_sine(self) -> None:
        """Sine wave has I:E ratio ≈ 1.0 (symmetric)."""
        fs = VERNIER_SAMPLE_RATE_HZ
        t = np.arange(0, 120, 1.0 / fs)
        force = np.sin(2 * np.pi * 0.2 * t) * 10.0

        features = compute_respiratory_features(force, fs=fs)
        if features["ie_ratio_mean"] is not None:
            assert abs(features["ie_ratio_mean"] - 1.0) < 0.5  # generous tolerance

    def test_duty_cycle(self) -> None:
        """Duty cycle for sine wave should be near 0.5."""
        fs = VERNIER_SAMPLE_RATE_HZ
        t = np.arange(0, 60, 1.0 / fs)
        force = np.sin(2 * np.pi * 0.2 * t) * 10.0

        features = compute_respiratory_features(force, fs=fs)
        if features["duty_cycle_mean"] is not None:
            assert abs(features["duty_cycle_mean"] - 0.5) < 0.15


# ── Tests: parse_and_analyze_vernier ─────────────────────────────────────────


class TestParseAndAnalyze:
    """Integration: parse + analyze in one step."""

    def test_full_pipeline(self) -> None:
        """End-to-end: parse XLSX → 20 Hz timeseries → respiratory features."""
        df = _sine_vernier_df(n_seconds=60.0, rate_hz=50.0, breath_freq=0.2)
        result = parse_and_analyze_vernier(_make_xlsx(df))

        assert result.respiratory_features is not None
        assert result.respiratory_features["n_breaths"] > 0
        assert result.respiratory_features["resp_rate_bpm"] is not None

    def test_mixed_frequency_resampling(self) -> None:
        """Non-uniform input timestamps are correctly resampled to 20 Hz."""
        # Simulate irregular sampling: 10-100 Hz random
        rng = np.random.default_rng(123)
        n = 2000
        intervals = rng.uniform(0.01, 0.1, n)
        t_unix = 1700000000.0 + np.cumsum(intervals)
        elapsed = t_unix - t_unix[0]
        force = np.sin(2 * np.pi * 0.2 * elapsed) * 5.0

        df = pd.DataFrame({"timestamp_unix": t_unix, "force": force})
        result = parse_vernier_xlsx(_make_xlsx(df))

        # Verify output is at 20 Hz
        ts = result.timeseries["timestamp_ms"].values
        diffs = np.diff(ts)
        assert np.all(diffs == 50)  # 50 ms = 20 Hz
        assert result.metadata["sample_rate_hz"] == VERNIER_SAMPLE_RATE_HZ


# ── Tests: Validation endpoint ───────────────────────────────────────────────

# These use the FastAPI test client if available; skip if httpx is not installed.

try:
    import httpx
    from httpx import AsyncClient
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not installed")
class TestVernierValidationEndpoint:
    """HTTP endpoint tests via ASGI test client."""

    @pytest.fixture
    def client(self):
        from app.main import app
        from httpx import ASGITransport
        transport = ASGITransport(app=app)
        return httpx.AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_valid_file(self, client: httpx.AsyncClient) -> None:
        """Valid Vernier file returns 200 with expected fields."""
        df = _sine_vernier_df(n_seconds=30.0, rate_hz=50.0)
        xlsx_bytes = _make_xlsx(df)

        resp = await client.post(
            "/api/v1/validate/csv/vernier",
            files={"file": ("test.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["sample_rate_hz"] == 20
        assert data["duration_s"] > 0

    @pytest.mark.asyncio
    async def test_invalid_file(self, client: httpx.AsyncClient) -> None:
        """Invalid file returns 422."""
        df = pd.DataFrame({"x": [1], "y": [2]})
        xlsx_bytes = _make_xlsx(df)

        resp = await client.post(
            "/api/v1/validate/csv/vernier",
            files={"file": ("bad.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["detail"]["valid"] is False

    @pytest.mark.asyncio
    async def test_empty_file_422(self, client: httpx.AsyncClient) -> None:
        """Empty Vernier file returns 422 with clear message."""
        df = pd.DataFrame({"timestamp_unix": [], "force": []})
        xlsx_bytes = _make_xlsx(df)

        resp = await client.post(
            "/api/v1/validate/csv/vernier",
            files={"file": ("empty.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert "at least 10" in data["detail"]["reason"]
