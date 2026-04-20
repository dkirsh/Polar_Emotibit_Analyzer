"""Typed domain models for signal and synchronization artifacts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalPoint:
    """One synchronized multimodal sample."""

    ts_ms: int
    hr_bpm: float
    eda_us: float


@dataclass(frozen=True)
class DriftModel:
    """Linear drift model mapping source timestamps to reference timeline."""

    slope: float
    intercept_ms: float


@dataclass(frozen=True)
class PiecewiseDriftModel:
    """Piecewise linear drift representation."""

    segments: list[DriftModel]
    breakpoints_ms: list[int]

    @property
    def n_segments(self) -> int:
        """Number of piecewise drift segments."""
        return len(self.segments)

    @property
    def is_trivial(self) -> bool:
        """Whether drift correction reduces to one linear mapping."""
        return self.n_segments <= 1

