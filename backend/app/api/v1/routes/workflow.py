"""HTTP surface for the six-stage workflow (the wizard's thin client backend).

Endpoints (per docs/ANALYZER_WIZARD_ARCHITECTURE):
  POST /workflow                  → start a run (body: input_dir, comparison, …)
  POST /workflow/{id}/advance     → continue (mode=auto|step)
  GET  /workflow/{id}             → state + any pending decisions
  POST /workflow/{id}/resolve     → submit choices for the current pause
  POST /workflow/{id}/rerun/{stg} → redo from a stage (downstream superseded)
  GET  /workflow/{id}/inspect/{sid} → single-subject raw+cleaned series + windows
  GET  /workflow/{id}/figure        → serve a generated PNG by name (fail-soft)

State is persisted to data/workflow_runs/<id>.json so a run resumes after the
app is closed (the spec's WorkflowState persistence). The SQLite canonical store
lives beside it. Single-process, single-writer — matches the repo's executor.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from app.services.workflow.state import WorkflowState
from app.services.workflow.orchestrator import Orchestrator
from app.services.workflow.canonical_store import CanonicalStore
from app.services.workflow import stages as _stages

router = APIRouter(tags=["workflow"], prefix="/workflow")

_RUNS_DIR = Path(os.environ.get("ANALYZER_DATA_DIR", "data")) / "workflow_runs"


def _paths(wid: str) -> tuple[Path, Path]:
    _RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return _RUNS_DIR / f"{wid}.json", _RUNS_DIR / f"{wid}.db"


def _save(s: WorkflowState) -> None:
    state_path, _ = _paths(s.workflow_id)
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s.to_dict()))
    os.replace(tmp, state_path)  # atomic, per the mutation discipline


def _load(wid: str) -> WorkflowState:
    state_path, _ = _paths(wid)
    if not state_path.exists():
        raise HTTPException(404, f"workflow {wid} not found")
    return WorkflowState.from_dict(json.loads(state_path.read_text()))


@router.post("")
def start(config: dict = Body(default_factory=dict)) -> dict:
    wid = uuid.uuid4().hex[:12]
    _, db = _paths(wid)
    s = WorkflowState(workflow_id=wid, db_path=str(db),
                      config=config, pause_before=config.pop("pause_before", []))
    orch = Orchestrator(s)
    try:
        orch.advance(mode=config.get("mode", "auto"))
    finally:
        orch.close()
    _save(s)
    return s.to_dict()


@router.post("/{wid}/advance")
def advance(wid: str, body: dict = Body(default_factory=dict)) -> dict:
    s = _load(wid)
    orch = Orchestrator(s)
    try:
        orch.advance(mode=body.get("mode", "auto"))
    finally:
        orch.close()
    _save(s)
    return s.to_dict()


@router.get("/{wid}")
def get_state(wid: str) -> dict:
    return _load(wid).to_dict()


@router.post("/{wid}/resolve")
def resolve(wid: str, choices: dict = Body(...)) -> dict:
    s = _load(wid)
    orch = Orchestrator(s)
    try:
        orch.resolve(choices, mode=choices.pop("mode", "auto"))
    finally:
        orch.close()
    _save(s)
    return s.to_dict()


@router.post("/{wid}/rerun/{stage}")
def rerun(wid: str, stage: str, body: dict = Body(default_factory=dict)) -> dict:
    s = _load(wid)
    orch = Orchestrator(s)
    try:
        orch.rerun(stage, mode=body.get("mode", "auto"))
    finally:
        orch.close()
    _save(s)
    return s.to_dict()


@router.get("/{wid}/inspect/{session_id}")
def inspect(wid: str, session_id: str) -> dict:
    s = _load(wid)
    store = CanonicalStore(s.db_path)
    try:
        if session_id not in store.sessions():
            raise HTTPException(404, f"session {session_id} not in run {wid}")
        return _stages.inspect(session_id, store)
    finally:
        store.close()


@router.get("/{wid}/figure")
def figure(wid: str, name: str):
    _, db = _paths(wid)
    fig = Path(db).parent / "figures" / Path(name).name  # basename only — no traversal
    if not fig.exists():
        raise HTTPException(404, f"figure {name} not found")
    return FileResponse(str(fig), media_type="image/png")
