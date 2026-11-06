"""The editor sends whatever is on screen, including half-drawn holds: the API must answer every
such spec with a 2xx or a 4xx carrying an error message, never a 5xx."""
import math
import shutil

import pytest
from hypothesis import HealthCheck, event, given, settings, strategies as st

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from conftest import ROOT  # noqa: E402
from holdgen_server.app import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("robust")
    shutil.copytree(ROOT / "holds", tmp / "holds")
    with TestClient(create_app(tmp / "holds", tmp / "builds"), raise_server_exceptions=False) as c:
        yield c


coord = st.floats(-120, 120, allow_nan=False, width=32)
pt = st.tuples(coord, coord).map(list)


@st.composite
def plausible_station(draw, x, n):
    """A section shaped like a hold (a bulge off the wall with jitter), lip_apex at its highest point."""
    y0 = draw(st.floats(0, 40))
    h = draw(st.floats(5, 60))
    d = draw(st.floats(0.5, 40))
    jit = draw(st.lists(st.tuples(st.floats(-6, 6), st.floats(-6, 6)), min_size=n, max_size=n))
    pts = []
    for i in range(n):
        a = math.pi * (i / (n - 1) - 0.5)
        z = 0.0 if i in (0, n - 1) else max(0.0, d * math.cos(a) + jit[i][0])
        pts.append([z, y0 + h / 2 + h / 2 * math.sin(a) + (0 if i in (0, n - 1) else jit[i][1])])
    apex = max(range(1, n - 1), key=lambda i: pts[i][1])
    return {"x": x, "points": pts, "landmarks": {"lip_apex": apex}, "corners": draw(st.lists(st.integers(1, n - 2), max_size=1))}


@st.composite
def plausible_spec(draw):
    """Valid-looking holds (same landmarks on every station, tips that meet, top view ends on the wall)
    with geometry anywhere from sensible to wild: these reach the loft and the mesher."""
    xs = sorted(draw(st.lists(st.floats(-80, 80), min_size=2, max_size=4, unique=True)))
    n = draw(st.integers(3, 9))
    s = {"schema": "hold-spec/1", "name": "fuzz", "stations": [draw(plausible_station(x, n)) for x in xs]}
    lo_x, hi_x = xs[0] - draw(st.floats(-10, 40)), xs[-1] + draw(st.floats(-10, 40))
    if draw(st.booleans()) and hi_x - lo_x > 1:
        tl, tr = [lo_x, draw(st.floats(0, 80))], [hi_x, draw(st.floats(0, 80))]
        inner = lambda: sorted(draw(st.lists(st.tuples(st.floats(lo_x + 0.1, hi_x - 0.1), st.floats(-20, 120)).map(list),
                                             max_size=4)))
        s["front_view"] = {"upper": [tl, *inner(), tr], "lower": [tl, *inner(), tr], "strength": draw(st.floats(0, 1))}
    if draw(st.booleans()) and hi_x - lo_x > 1:
        inner = sorted(draw(st.lists(st.tuples(st.floats(lo_x + 0.1, hi_x - 0.1), st.floats(0, 50)).map(list),
                                     min_size=1, max_size=5)))
        s["top_view"] = {"points": [[lo_x, 0.0], *inner, [hi_x, 0.0]], "strength": draw(st.floats(0, 1))}
    if draw(st.booleans()):
        s["mounting"] = {"screws": draw(st.lists(st.tuples(st.floats(-90, 90), st.floats(0, 90)).map(list), max_size=3))}
    return s


@st.composite
def any_spec(draw):
    """Anything shaped roughly like a spec: empty, one station, short or crossed views, points anywhere."""
    sts = draw(st.lists(st.fixed_dictionaries({"x": coord, "points": st.lists(pt, max_size=8),
                                               "landmarks": st.sampled_from([{}, {"lip_apex": 1}, {"lip_apex": 9}])}),
                        max_size=4))
    s = {"schema": "hold-spec/1", "name": "fuzz", "stations": sts}
    if draw(st.booleans()):
        s["front_view"] = {"upper": draw(st.lists(pt, max_size=5)), "lower": draw(st.lists(pt, max_size=5))}
    if draw(st.booleans()):
        s["top_view"] = {"points": draw(st.lists(pt, max_size=6))}
    return s


specs = st.one_of(plausible_spec(), plausible_spec(), plausible_spec(), any_spec())


def _ok(r):
    assert r.status_code < 500, r.text[:300]
    if r.status_code >= 400:
        assert r.json()["error"]


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture,
                                                                  HealthCheck.too_slow])
@given(spec=specs, x=coord)
def test_editor_endpoints_never_5xx(client, spec, x):
    _ok(client.post("/api/validate", json={"spec": spec}))
    r = client.post("/api/preview", json={"spec": spec})
    _ok(r)
    event(f"preview {r.status_code}")
    r = client.post("/api/section-at", json={"spec": spec, "x": x})
    _ok(r)
    event(f"section-at {r.status_code}")


def test_near_flat_section_at_is_not_a_500(client):
    """fit simplified a nearly straight section to 2 points, which the response model rejects."""
    st_ = lambda x: {"x": x, "points": [[0, 10], [0.01, 20], [0, 30]], "landmarks": {}}
    r = client.post("/api/section-at", json={"spec": {"schema": "hold-spec/1", "name": "t", "stations": [st_(-30), st_(30)]},
                                             "x": 0})
    assert r.status_code == 200 and len(r.json()["station"]["points"]) >= 3
