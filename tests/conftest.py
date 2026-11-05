import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def ravage_raw() -> dict:
    """Ravage v2 rebuilt from 5 hand-fit sections (+ loose front/top views, 2 screws)."""
    return load_fixture("ravage_5st_handfit.json")


@pytest.fixture
def ravage(ravage_raw) -> dict:
    from holdgen import spec
    return spec.normalize(copy.deepcopy(ravage_raw))


@pytest.fixture
def simple_raw() -> dict:
    """Two plain stations, no views: rounded caps, fast to build."""
    pts = [[0, 0], [8, 10], [12, 25], [10, 32], [4, 30], [0, 28]]
    return {
        "schema": "hold-spec/1", "name": "simple",
        "stations": [
            {"x": -30, "points": pts, "landmarks": {"lip_apex": 3}},
            {"x": 30, "points": [[z * 1.2, y * 1.1 + 2] for z, y in pts], "landmarks": {"lip_apex": 3}},
        ],
        "mounting": {"screws": [[0, 12]]},
        "build": {"voxel": 0.5},
    }
