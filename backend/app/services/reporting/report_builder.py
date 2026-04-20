"""Report rendering utilities."""

from __future__ import annotations

from app.schemas.analysis import FeatureSummary
from app.services.ai.adapters import NON_DIAGNOSTIC_NOTICE


def build_markdown_report(feature_summary: FeatureSummary, quality_flags: list[str]) -> str:
    """Build a markdown report for human review and export."""
    flags = "\n".join(f"- {flag}" for flag in quality_flags) if quality_flags else "- None"

    # Frequency-domain HRV section (only when available)
    freq_section = ""
    if feature_summary.lf_ms2 is not None:
        vlf_line = (
            f"- VLF Power: {feature_summary.vlf_ms2:.2f} ms²\n"
            if feature_summary.vlf_ms2 is not None
            else "- VLF Power: unavailable (recording too short)\n"
        )
        freq_section = (
            "\n## Frequency-Domain HRV\n"
            f"{vlf_line}"
            f"- LF Power: {feature_summary.lf_ms2:.2f} ms²\n"
            f"- HF Power: {feature_summary.hf_ms2:.2f} ms²\n"
        )
        if feature_summary.lf_hf_ratio is not None:
            freq_section += f"- LF/HF Ratio: {feature_summary.lf_hf_ratio:.4f}\n"

    return (
        "# EmotiBit + Polar Analysis Report\n\n"
        "## Notice\n"
        f"- {NON_DIAGNOSTIC_NOTICE}\n\n"
        "## Feature Summary\n"
        f"- RMSSD: {feature_summary.rmssd_ms:.2f} ms\n"
        f"- SDNN: {feature_summary.sdnn_ms:.2f} ms\n"
        f"- Mean HR: {feature_summary.mean_hr_bpm:.2f} bpm\n"
        f"- EDA Mean: {feature_summary.eda_mean_us:.3f} uS\n"
        f"- EDA Phasic Index: {feature_summary.eda_phasic_index:.3f}\n"
        f"- Stress Score (experimental, unvalidated): {feature_summary.stress_score:.3f}\n"
        f"- RR Source: {feature_summary.rr_source}\n"
        f"{freq_section}\n"
        "## Quality Flags\n"
        f"{flags}\n"
    )
