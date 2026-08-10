"""Severity test for the workflow HTTP surface — proves the pipeline is reachable
end-to-end through the API (last-mile: computed ≠ wired-in until the route works).

Attacks: start must pause at define without a comparison; resolve must finish the
run; inspect must return a single subject's series; the figure endpoint must serve
a PNG the Visualise stage wrote; persistence must let a second request resume.
"""
from __future__ import annotations

import os
import tempfile

import pandas as pd
from fastapi.testclient import TestClient


def _make_dir(tmp):
    d = os.path.join(tmp, "in"); os.makedirs(d)
    t0 = 1_700_000_000_000
    for sub, pm, npm in [("p012_G1", 1.0, 2.0), ("p014_G3", 1.5, 2.5), ("p016_G4", 1.2, 2.2)]:
        rows = [(t0 + i, pm) for i in range(0, 10000, 100)] + \
               [(t0 + i, npm) for i in range(20000, 30000, 100)]
        pd.DataFrame(rows, columns=["timestamp_ms", "eda_us"]).to_csv(
            os.path.join(d, f"{sub}_emotibit.csv"), index=False)
        pd.DataFrame([
            {"event_code": "plants_onset", "utc_ms": t0}, {"event_code": "plants_offset", "utc_ms": t0 + 9999},
            {"event_code": "no_plants_onset", "utc_ms": t0 + 20000}, {"event_code": "no_plants_offset", "utc_ms": t0 + 30000},
        ]).to_csv(os.path.join(d, f"{sub}_markers.csv"), index=False)
    return d


def test_workflow_http_start_resolve_inspect_figure():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ANALYZER_DATA_DIR"] = tmp  # isolate run storage
        import importlib
        from app.api.v1.routes import workflow as wf
        importlib.reload(wf)  # pick up the patched data dir
        from app.main import app
        client = TestClient(app)
        d = _make_dir(tmp)

        r = client.post("/api/v1/workflow", json={"input_dir": d})
        assert r.status_code == 200
        s = r.json(); wid = s["workflow_id"]
        assert s["current_stage"] == "define" and s["pending"], "should pause at define"

        r = client.post(f"/api/v1/workflow/{wid}/resolve",
                        json={"comparison": {"conditions": ["plants", "no_plants"],
                                             "measures": ["eda_tonic"]}})
        s = r.json()
        assert s["current"] >= 6, "run finished after resolve"
        block = s["artifacts"]["analyse"]["measures"]["eda_tonic"]["paired"]
        assert block["n"] == 3

        # GET resumes from persisted state
        assert client.get(f"/api/v1/workflow/{wid}").json()["workflow_id"] == wid

        # inspect a single subject
        ins = client.get(f"/api/v1/workflow/{wid}/inspect/p012").json()
        assert ins["session_id"] == "p012" and len(ins["eda"]) > 0

        # the Visualise stage wrote a figure; serve it
        fig_path = s["artifacts"]["visualise"]["figures"]["eda_tonic"]
        name = os.path.basename(fig_path)
        fr = client.get(f"/api/v1/workflow/{wid}/figure", params={"name": name})
        assert fr.status_code == 200 and fr.headers["content-type"] == "image/png"
        os.environ.pop("ANALYZER_DATA_DIR", None)
