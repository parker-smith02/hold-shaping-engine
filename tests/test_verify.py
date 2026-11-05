"""Which stations a feature reaches (those are expected to deviate from the drawing)."""
import json

from conftest import ROOT
from holdgen.verify import features_touching


def test_example_groove_reaches_only_the_station_it_crosses():
    spec = json.loads((ROOT / "holds" / "ravage_example.json").read_text(encoding="utf-8"))
    hits = {st["x"]: features_touching(spec["features"], st["x"]) for st in spec["stations"]}
    assert hits == {-55.0: [], -25.0: [], -0.1: [], 25.1: [0], 55.1: []}


def test_reach_scales_with_size_and_depth():
    dent = {"type": "dent", "center": [0, 30, 20], "size": [8, 8, 4], "depth": 1.5}
    assert features_touching([dent], 14.0) == [0]           # 8 * sqrt(ln 30) = 14.8
    assert features_touching([dent], 15.0) == []
    assert features_touching([{**dent, "depth": -0.04}], 0.0) == []   # too shallow to matter anywhere
