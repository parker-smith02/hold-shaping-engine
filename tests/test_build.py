"""Full SDF builds. The Ravage rebuild is the regression baseline for fidelity and shape."""
import json

import pytest

from conftest import load_fixture
from holdgen import pipeline, spec as spec_mod


def test_small_build_is_watertight_and_faithful(simple_raw, tmp_path):
    spec = spec_mod.normalize(simple_raw)
    summary = pipeline.build_to_dir(spec, str(tmp_path), previews=False)
    assert summary["mesh"]["watertight"]
    vox = spec["build"]["voxel"]                                     # 0.5 mm here, coarse for speed
    for st in summary["stations"]:
        assert st["deviation_mm"]["max"] < 1.5 * vox, st             # smoothing on a tight lip costs ~1 voxel
        assert st["deviation_mm"]["mean"] < 0.1 * vox, st
    assert {f for f in pipeline.OUTPUT_FILES if (tmp_path / f).exists()} >= {"hold.stl", "report.md", "report.json", "overlay.png"}


@pytest.mark.slow
def test_ravage_baseline(tmp_path):
    """Ravage v2 from 5 hand-fit sections at 0.3 mm. Baseline recorded 2026-11: 157.4 x 60.0 x 21.8 mm,
    ~84 cm3, station deviation <= 0.21 mm away from screw holes."""
    s = spec_mod.normalize(load_fixture("ravage_5st_handfit.json"))
    summary = pipeline.build_to_dir(s, str(tmp_path), previews=False)
    m = summary["mesh"]
    assert m["watertight"]
    assert m["size_mm"][0] == pytest.approx(157.4, abs=1.0)
    assert m["size_mm"][1] == pytest.approx(60.0, abs=1.0)
    assert m["size_mm"][2] == pytest.approx(21.8, abs=0.5)
    assert m["volume_cm3"] == pytest.approx(84.0, rel=0.03)
    for st in summary["stations"]:
        if not st["cuts_screw"] and not st["features"]:
            assert st["deviation_mm"]["max"] < 0.25, st
            assert st["deviation_mm"]["mean"] < 0.03, st
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["name"] == s["name"]


@pytest.mark.slow
@pytest.mark.parametrize("name", ["curl.json", "features.json"])
def test_edge_cases_build_watertight(name, tmp_path):
    summary = pipeline.build_to_dir(spec_mod.normalize(load_fixture(name)), str(tmp_path), previews=False)
    assert summary["mesh"]["watertight"]
