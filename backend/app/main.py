"""FastAPI application entrypoint for the Polar-EmotiBit Analyzer.

Scope: file-only post-hoc analysis. The endpoints accept pre-synched pairs
of Polar H10 and EmotiBit CSVs plus optional event markers, run the V2.1
pipeline, and return the structured analysis response. Device scanning,
real-time streaming, and recording control are deliberately NOT exposed —
see docs/GUI_SCOPE_FILE_ONLY_2026-04-20.md.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import analysis, validate
from app.schemas.analysis import HealthResponse

app = FastAPI(
    title="Polar-EmotiBit Analyzer API",
    version="2.1.0",
    description=(
        "Post-hoc synchronization and feature extraction for pre-recorded "
        "Polar H10 + EmotiBit sessions. Not a live-streaming service."
    ),
)

# CORS is permissive in dev (the Vite dev server runs on :5173). Tighten
# this when deploying beyond a researcher's own machine.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe."""
    return HealthResponse(ok=True, version="2.1.0", scope="file-only post-hoc")


app.include_router(analysis.router, prefix="/api/v1")
app.include_router(validate.router, prefix="/api/v1")
