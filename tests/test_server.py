"""HTTP API: contract, error mapping, library and build jobs."""
import copy
import shutil
import time

import pytest

pytest.importorskip("fastapi", reason="install the server extra: pip install -e '.[server,dev]'")
from fastapi.testclient import TestClient  # noqa: E402

from conftest import ROOT  # noqa: E402
from holdgen_server.app import create_app  # noqa: E402
from holdgen_server.models import PreviewResponse  # noqa: E402


@pytest.fixture
def client(tmp_path):
    holds = tmp_path / "holds"
    shutil.copytree(ROOT / "holds", holds)
    app = create_app(holds, tmp_path / "builds")
    with TestClient(app) as c:
        yield c


def test_health_schema_and_docs(client):
    assert client.get("/api/health").json()["ok"] is True
    assert client.get("/api/schema").json()["title"] == "hold-spec/1"
    assert client.get("/api/openapi.json").status_code == 200


def test_preview_matches_contract(client):
    spec = client.get("/api/holds/ravage_example").json()
    r = client.post("/api/preview", json={"spec": spec})
    assert r.status_code == 200
    PreviewResponse.model_validate(r.json())
    assert r.json()["mesh"]["triangle_count"] > 10_000


def test_invalid_spec_is_422_with_issues(client):
    spec = client.get("/api/holds/ravage_example").json()
    spec["stations"][0]["points"][0][0] = 3
    r = client.post("/api/preview", json={"spec": spec})
    assert r.status_code == 422
    assert r.json()["issues"][0]["code"] == "station.root_off_wall"


def test_malformed_request_is_400(client):
    r = client.post("/api/preview", json={"spek": {}})
    assert r.status_code == 400 and r.json()["error"].startswith("bad request")


def test_section_at(client):
    spec = client.get("/api/holds/ravage_example").json()
    r = client.post("/api/section-at", json={"spec": spec, "x": -40})
    assert set(r.json()["station"]["landmarks"]) == {"face_out", "lip_apex"}
    assert client.post("/api/section-at", json={"spec": spec, "x": 400}).status_code == 422


def test_library_crud(client):
    spec = client.get("/api/holds/ravage_example").json()
    r = client.put("/api/holds/copy_1", json=spec)
    assert r.status_code == 200 and r.json()["name"] == "copy_1"
    assert client.get("/api/holds/copy_1").json()["name"] == "copy_1"       # name follows the path
    assert "copy_1" in [h["name"] for h in client.get("/api/holds").json()["holds"]]
    assert client.put("/api/holds/Bad%20Name", json=spec).status_code == 400
    assert client.put("/api/holds/broken", json={"stations": "nope"}).status_code == 422
    draft = copy.deepcopy(spec)
    draft["stations"][0]["points"][0][0] = 3                                # semantic error: allowed in drafts
    assert client.put("/api/holds/draft", json=draft).json()["issues"]
    assert client.delete("/api/holds/copy_1").status_code == 204
    assert client.delete("/api/holds/copy_1").status_code == 404


def test_build_job_lifecycle(client):
    spec = client.get("/api/holds/ravage_example").json()
    spec["build"]["voxel"] = 0.8
    r = client.post("/api/builds", json={"spec": spec})
    assert r.status_code == 202
    job = r.json()
    seen = set()
    for _ in range(240):
        st = client.get(f"/api/builds/{job['id']}").json()
        seen.add(st["state"])
        if st["state"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert st["state"] == "done", st
    assert "running" in seen
    assert st["report"]["mesh"]["watertight"]
    assert "hold.stl" in st["files"]
    stl = client.get(f"/api/builds/{job['id']}/files/hold.stl")
    assert stl.status_code == 200 and len(stl.content) > 1000
    assert client.get(f"/api/builds/{job['id']}/files/status.json").status_code == 404
    assert client.get("/api/builds/not-a-job").status_code == 404
