"""Preview payload: closed mesh, sane readouts, features displaced where anchored, fast enough to drag."""
import base64
import copy
import time

import numpy as np
import pytest

from conftest import load_fixture
from holdgen import fit, preview, spec as spec_mod


def decode(p):
    V = np.frombuffer(base64.b64decode(p["mesh"]["positions"]), "<f4").reshape(-1, 3)
    T = np.frombuffer(base64.b64decode(p["mesh"]["indices"]), "<u4").reshape(-1, 3).astype(np.int64)
    return V, T


def assert_closed_outward(V, T):
    E = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), 1)
    _, cnt = np.unique(E[:, 0] * len(V) + E[:, 1], return_counts=True)
    assert (cnt == 2).all(), "every edge must be shared by exactly two triangles"
    v0, v1, v2 = (V[T[:, k]].astype(np.float64) for k in range(3))
    assert np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() > 0, "normals must face outward"


@pytest.mark.parametrize("name", ["ravage_5st_handfit.json", "curl.json", "features.json"])
def test_preview_mesh_is_closed(name):
    p = preview.preview(spec_mod.normalize(load_fixture(name)))
    V, T = decode(p)
    assert np.isfinite(V).all()
    assert_closed_outward(V, T)
    assert len(V) == p["mesh"]["vertex_count"] and len(T) == p["mesh"]["triangle_count"]


def test_preview_caps_mesh_is_closed(simple_raw):
    p = preview.preview(spec_mod.normalize(simple_raw))
    assert p["loft"]["tips"] == {"left": "cap", "right": "cap"}
    assert_closed_outward(*decode(p))


def test_readouts_cover_stations_and_midpoints(ravage):
    p = preview.preview(ravage)
    kinds = [r["kind"] for r in p["readouts"]]
    assert kinds.count("station") == len(ravage["stations"])
    assert kinds.count("between") == len(ravage["stations"]) - 1
    mid = next(r for r in p["readouts"] if r["kind"] == "station" and r["x"] == ravage["stations"][2]["x"])
    assert 20 < mid["readouts"]["depth"] < 30                       # the 25 mm crimp
    assert len(p["screws"]) == 2 and all(s["face_z"] > 10 for s in p["screws"])


def test_features_move_only_their_neighbourhood(ravage):
    base = decode(preview.preview(ravage))[0]
    s = copy.deepcopy(ravage)
    s["features"] = [{"type": "dent", "surface": "front", "center": [0.0, 40.0], "size": [6, 6, 4], "depth": 2.0}]
    moved = decode(preview.preview(s))[0]
    d = np.linalg.norm(moved - base, axis=1)
    near = (np.abs(base[:, 0]) < 4) & (np.abs(base[:, 1] - 40) < 4) & (base[:, 2] > 5)
    assert d[near].max() > 1.0
    assert d[np.abs(base[:, 0]) > 25].max() < 1e-4
    assert d[base[:, 2] < 0.05].max() == 0                          # the back stays flat


def test_preview_is_interactive_speed(ravage):
    preview.preview(ravage)
    t = time.perf_counter()
    for _ in range(3):
        preview.preview(ravage)
    assert (time.perf_counter() - t) / 3 < 0.25


def test_section_at_matches_loft_and_keeps_landmarks(ravage):
    from scipy.spatial import cKDTree

    from holdgen import curves
    from holdgen.loft import Loft
    st = fit.section_at(ravage, -40.0)
    assert set(st["landmarks"]) == {"face_out", "lip_apex"}
    P, _ = Loft(ravage).at([-40.0])
    dense, _ = curves.eval_open(st["points"])
    d, _ = cKDTree(dense).query(P[0][1:-1])
    assert d.max() < 0.15
    with pytest.raises(ValueError):
        fit.section_at(ravage, 500.0)
