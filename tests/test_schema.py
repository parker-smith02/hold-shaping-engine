"""hold-spec/1 model: structural validation, semantic checks, generated artifacts."""
import copy
import json
import subprocess
import sys

import jsonschema
import pytest

from conftest import FIXTURES, ROOT
from holdgen import schema, spec as spec_mod

ALL_SPECS = sorted(FIXTURES.glob("*.json")) + sorted((ROOT / "holds").glob("*.json"))


@pytest.mark.parametrize("path", ALL_SPECS, ids=lambda p: p.name)
def test_fixtures_and_holds_are_valid(path):
    raw = json.loads(path.read_text())
    model, issues = schema.validate(raw)
    assert model is not None
    assert not [i for i in issues if i.level == "error"], issues
    jsonschema.validate(raw, schema.json_schema())        # the published schema agrees with the model


def codes(raw) -> set[str]:
    _, issues = schema.validate(raw)
    return {i.code for i in issues}


def test_structural_errors_are_issues_not_exceptions(simple_raw):
    raw = copy.deepcopy(simple_raw)
    raw["stations"][0]["points"] = [[0, 0], [1, 1]]
    raw["unknown_field"] = 1
    c = codes(raw)
    assert "schema.too_short" in c and "schema.extra_forbidden" in c


@pytest.mark.parametrize("mutate,code", [
    (lambda r: r["stations"][0]["points"].__setitem__(0, [2.0, 0.0]), "station.root_off_wall"),
    (lambda r: r["stations"][0]["points"].__setitem__(2, [-1.0, 25.0]), "station.behind_wall"),
    (lambda r: r["stations"][0].__setitem__("points", r["stations"][0]["points"][::-1]), "station.direction"),
    (lambda r: r["stations"][1].__setitem__("x", -30), "station.duplicate_x"),
    (lambda r: r["stations"][0]["landmarks"].__setitem__("lip_apex", 0), "landmark.range"),
    (lambda r: r["stations"][0]["landmarks"].__setitem__("bottom_root", 0), "landmark.reserved"),
    (lambda r: r["stations"][0]["landmarks"].__setitem__("face_out", 3), "landmark.shared_point"),
    (lambda r: r["stations"][0]["corners"].append(0) if "corners" in r["stations"][0] else r["stations"][0].__setitem__("corners", [0]), "corner.range"),
    (lambda r: r["mounting"].__setitem__("countersink_dia", 4.0), "mounting.countersink"),
    (lambda r: r.__setitem__("features", [{"type": "dent", "center": [0, 20], "depth": 1}]), "feature.surface"),
])
def test_semantic_rules(simple_raw, mutate, code):
    raw = copy.deepcopy(simple_raw)
    mutate(raw)
    assert code in codes(raw)


def test_landmark_mismatch_blames_the_odd_station(ravage_raw):
    raw = copy.deepcopy(ravage_raw)
    raw["stations"][0]["landmarks"]["extra"] = 2
    _, issues = schema.validate(raw)
    mism = [i for i in issues if i.code == "landmark.mismatch"]
    assert len(mism) == 1 and mism[0].path[:2] == ["stations", 0]


def test_lowering_sorts_stations_and_adds_roots(simple_raw):
    raw = copy.deepcopy(simple_raw)
    raw["stations"].reverse()
    s = spec_mod.normalize(raw)
    assert [t["x"] for t in s["stations"]] == [-30, 30]
    assert s["landmark_order"] == ["bottom_root", "lip_apex", "ledge_root"]
    assert s["stations"][0]["landmarks"]["ledge_root"] == len(s["stations"][0]["points"]) - 1


def test_normalize_raises_with_issues(simple_raw):
    raw = copy.deepcopy(simple_raw)
    raw["stations"] = raw["stations"][:1]
    with pytest.raises(spec_mod.SpecError) as e:
        spec_mod.normalize(raw)
    assert e.value.issues


def test_generated_files_are_current():
    """types.gen.ts, hold-spec.schema.json and curves.golden.json must match their generators."""
    r = subprocess.run([sys.executable, "-m", "holdgen_server.codegen", "--check"], cwd=ROOT,
                       env={"PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    g = subprocess.run([sys.executable, "tools/gen_golden.py", "--check"], cwd=ROOT, capture_output=True, text=True)
    assert g.returncode == 0, "run: python tools/gen_golden.py"
