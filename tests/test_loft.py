"""Loft invariants. The central promise: drawn sections are authoritative and the loose views
can never move them. Property-tested over random outlines and strengths."""
import copy

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from holdgen import curves, loft, spec as spec_mod

SETTINGS = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


def perturbed_views(raw: dict, seed: int, amp: float, strength_f: float, strength_t: float) -> dict:
    """The spec with its front/top views wobbled and stretched by a seeded random field."""
    r = copy.deepcopy(raw)
    rng = np.random.default_rng(seed)
    sx = 1 + 0.1 * rng.uniform(-1, 1)
    tips = amp * rng.standard_normal(2)                       # the edges share their tips: move them together
    edges = {}
    for k in ("upper", "lower"):
        e = np.array(r["front_view"][k])
        e[1:-1, 1] += amp * rng.standard_normal(len(e) - 2)
        e[[0, -1], 1] += tips
        e[:, 0] *= sx
        edges[k] = e.tolist()
    r["front_view"] = {**edges, "strength": strength_f}
    t = np.array(r["top_view"]["points"])
    t[1:-1, 1] = np.maximum(0.5, t[1:-1, 1] + amp * 0.5 * rng.standard_normal(len(t) - 2))
    r["top_view"] = {"points": t.tolist(), "strength": strength_t}
    return r


@SETTINGS
@given(seed=st.integers(0, 2**32 - 1), amp=st.floats(0, 8), sf=st.floats(0, 1), stt=st.floats(0, 1))
def test_views_never_move_a_station(ravage_raw, seed, amp, sf, stt):
    s = spec_mod.normalize(perturbed_views(ravage_raw, seed, amp, sf, stt))
    L = loft.Loft(s)
    P, ok = L.at(L.xs)
    assert ok.all()
    np.testing.assert_allclose(P, L.M, atol=1e-9)


@SETTINGS
@given(seed=st.integers(0, 2**32 - 1), amp=st.floats(0.5, 8))
def test_strength_zero_is_pure_section_blend(ravage_raw, seed, amp):
    s = spec_mod.normalize(perturbed_views(ravage_raw, seed, amp, 0.0, 0.0))
    L = loft.Loft(s)
    xq = np.linspace(L.xs[0], L.xs[-1], 37)
    P, _ = L.at(xq)
    np.testing.assert_allclose(P, L._pchip(xq).reshape(P.shape), atol=1e-12)


def test_stations_match_drawn_splines(ravage):
    """Matched points of each station lie on that station's spline (checked against a 10x finer
    evaluation, so the tolerance covers only chord error, not sample spacing)."""
    from scipy.spatial import cKDTree
    L = loft.Loft(ravage)
    for i, st_ in enumerate(ravage["stations"]):
        fine, _ = curves.eval_open(st_["points"], st_.get("corners", []), step=0.002)
        d, _ = cKDTree(fine).query(L.M[i])
        assert d.max() < 0.005


def test_tip_leaves_end_station_without_a_crease(ravage):
    """C1 at the outermost stations: one-sided slopes of every matched coordinate agree."""
    L = loft.Loft(ravage)
    h = 1e-4
    for xe, sgn in ((L.xs[0], -1), (L.xs[-1], 1)):
        P, ok = L.at([xe - 2 * h * sgn, xe - h * sgn, xe, xe + h * sgn, xe + 2 * h * sgn])
        assert ok.all()
        inner = (P[2] - P[1]) / h
        outer = (P[3] - P[2]) / h
        assert np.abs(inner - outer).max() < 1e-3


def test_caps_without_views(simple_raw):
    L = loft.Loft(spec_mod.normalize(simple_raw))
    assert L.tip["left"]["kind"] == "cap" and L.tip["right"]["kind"] == "cap"
    assert (L.x_min, L.x_max) == (-30, 30)


@settings(max_examples=60, deadline=None)
@given(n=st.integers(3, 40), seed=st.integers(0, 2**32 - 1), q=st.integers(1, 300))
def test_fast_extents_equal_reference(n, seed, q):
    rng = np.random.default_rng(seed)
    ang = np.sort(rng.uniform(0, 2 * np.pi, n))
    poly = np.stack([np.cos(ang) * rng.uniform(5, 50, n), np.sin(ang) * rng.uniform(5, 50, n)], 1).round(1)
    xq = np.concatenate([rng.uniform(-60, 60, q), poly[:, 0]])      # include exact vertex abscissae
    a, b = loft._extents(poly, xq), loft._extents_dense(poly, xq)
    for u, v in zip(a, b):
        np.testing.assert_array_equal(np.isnan(u), np.isnan(v))
        np.testing.assert_allclose(u[~np.isnan(u)], v[~np.isnan(v)], atol=1e-9)


def test_curves_pass_through_points_and_respect_corners():
    pts = np.array([[0, 0], [6, 12], [10, 25], [7, 31], [0, 29]], float)
    dense, idx = curves.eval_open(pts, [2], step=0.01)
    np.testing.assert_allclose(dense[idx], pts, atol=1e-12)
    k = idx[2]
    t1 = np.arctan2(*(dense[k] - dense[k - 1])[::-1])
    t2 = np.arctan2(*(dense[k + 1] - dense[k])[::-1])
    assert abs(t2 - t1) > 0.1
    with pytest.raises(ValueError):
        curves.eval_closed(pts[:2])
