"""Cohort-aware ingestion, orchestration, storage, and export.

This package adds multi-subject batch processing on top of the existing
single-session analyzer pipeline (``app.services.processing.pipeline``)
without modifying it. The existing ``run_analysis(emotibit_df, polar_df)``
function is the per-subject worker; this package is the loop around it
plus the persistence and export layers.

Design principle: subject is a first-class entity at every layer. Each
file is partitioned to its subject at ingestion time; the orchestrator
runs the existing per-session pipeline once per subject; results land in
a SQLite database keyed by ``(subject_id, session_id)``; exports query
that database.

Sub-modules:
    partition   — recursive directory walker, subject-aware file partitioning
    orchestrator — loop wrapper around ``run_analysis`` for cohorts
    store       — SQLite persistence layer
    export      — long-format CSV + per-subject-sheet XLSX
"""

from app.services.cohort.partition import (
    SubjectBundle,
    IngestionReport,
    partition_directory,
    partition_zip,
    NATIVE_EMOTIBIT_CHANNEL_MAP,
)

__all__ = [
    "SubjectBundle",
    "IngestionReport",
    "partition_directory",
    "partition_zip",
    "NATIVE_EMOTIBIT_CHANNEL_MAP",
]
