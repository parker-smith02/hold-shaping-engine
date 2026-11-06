"""Editor end to end: the built web app (web/dist) served by the real API, driven in Chromium.

Run:  (cd web && npm run build) && pytest -m e2e
Uses HOLDGEN_WEB_DIST if set, else web/dist; skips when neither has an index.html.
The page exposes window.holdgen = {store, preview, panes, view3d}: tests read state and map
mm to screen through it, but every edit goes through real pointer events and buttons.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urljoin

import pytest

from conftest import ROOT

pytestmark = pytest.mark.e2e

uvicorn = pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

WEB_DIST = Path(os.environ.get("HOLDGEN_WEB_DIST", ROOT / "web" / "dist"))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    if not (WEB_DIST / "index.html").exists():
        pytest.skip(f"no built web app at {WEB_DIST}: run `npm run build` in web/")
    from holdgen_server.app import create_app

    tmp = tmp_path_factory.mktemp("e2e")
    holds = tmp / "holds"
    shutil.copytree(ROOT / "holds", holds)
    app = create_app(holds, tmp / "builds", WEB_DIST)
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(200):
        if srv.started:
            break
        time.sleep(0.05)
    assert srv.started, "uvicorn did not start"
    yield {"url": f"http://127.0.0.1:{port}", "holds": holds}
    srv.should_exit = True                       # runs the lifespan shutdown (build pool)
    th.join(timeout=15)
    assert not th.is_alive(), "server did not shut down"


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _open(browser, url):
    ctx = browser.new_context(viewport={"width": 1600, "height": 1000})   # fresh context: no saved draft
    pg = ctx.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    pg.goto(url)
    return ctx, pg, errors


@pytest.fixture
def page(browser, server):
    """The editor with holds/ravage_example.json open."""
    ctx, pg, errors = _open(browser, f"{server['url']}/?hold=ravage_example")
    _wait_preview(pg)
    yield pg
    ctx.close()
    assert not errors, errors


@pytest.fixture
def blank(browser, server):
    """The editor as a first-time visitor sees it: an empty hold."""
    ctx, pg, errors = _open(browser, f"{server['url']}/")
    pg.wait_for_function("() => window.holdgen && window.holdgen.preview.state.hint")
    yield pg
    ctx.close()
    assert not errors, errors


def _wait_preview(pg, after_seq: int | None = None, timeout: float = 15_000) -> None:
    """Wait until the preview holds fresh geometry (newer than `after_seq` if given)."""
    pg.wait_for_function(
        """(after) => { const p = window.holdgen?.preview;
             return p && p.state.data && !p.state.pending && !p.state.stale && !p.state.error
                    && (after === null || p.seq > after); }""",
        arg=after_seq, timeout=timeout)


def _js(pg, expr: str, arg=None):
    return pg.evaluate(f"(arg) => {{ const {{store, preview, panes, view3d}} = window.holdgen; return {expr}; }}", arg)


def _screen(pg, pane: str, x: float, y: float) -> tuple[float, float]:
    """Client coordinates of the world point (x, y) mm in a 2D pane."""
    return tuple(_js(pg, """(() => { const p = panes[arg.pane]; const s = p.toScreen(arg.x, arg.y);
                              const r = p.cv.getBoundingClientRect(); return [r.left + s[0], r.top + s[1]]; })()""",
                     {"pane": pane, "x": x, "y": y}))


def _drag(pg, a, b, steps: int = 8) -> None:
    pg.mouse.move(*a)
    pg.mouse.down()
    pg.mouse.move(*b, steps=steps)
    pg.mouse.up()


def _tool(pg, pane_tools_id: str, label: str) -> None:
    pg.locator(f"#{pane_tools_id} button", has_text=label).first.click()


def test_loads_hold_and_renders_preview(page):
    assert page.input_value("#holdName") == "ravage_example"
    assert _js(page, "preview.state.mesh.indices.length / 3") > 10_000
    assert "157" in page.text_content("#sizeLabel")
    assert page.locator("#roTable tr").count() > 5
    assert page.locator("#cv3d").bounding_box()["width"] > 200


def test_drag_section_point_updates_preview_and_undo_restores(page):
    st_i = _js(page, "store.spec.stations.findIndex(s => Math.abs(s.x + 0.1) < 1e-6)")
    page.locator("#stationChips button", has_text="-0.1").click()
    j = _js(page, "store.spec.stations[arg].landmarks.face_out", st_i)
    before = _js(page, "store.spec.stations[arg.i].points[arg.j]", {"i": st_i, "j": j})
    seq = _js(page, "preview.seq")

    a = _screen(page, "section", *before)
    _drag(page, a, (a[0] + 20, a[1]))             # outward (+z)
    _wait_preview(page, seq)

    after = _js(page, "store.spec.stations[arg.i].points[arg.j]", {"i": st_i, "j": j})
    assert after[0] > before[0] + 1.0
    assert abs(after[1] - before[1]) < 0.5
    assert page.is_enabled("#btnUndo")
    assert _js(page, "preview.state.latencyMs") < 2000

    seq = _js(page, "preview.seq")
    page.click("#btnUndo")
    _wait_preview(page, seq)
    assert _js(page, "store.spec.stations[arg.i].points[arg.j]", {"i": st_i, "j": j}) == before


def test_add_station_from_front_view(page):
    n0 = _js(page, "store.spec.stations.length")
    _tool(page, "toolsFront", "+ Station")
    page.mouse.click(*_screen(page, "front", -40, 25))
    page.wait_for_function("(n) => window.holdgen.store.spec.stations.length === n + 1", arg=n0)
    st = _js(page, "store.spec.stations.find(s => Math.abs(s.x + 40) < 0.6)")
    assert st is not None, _js(page, "store.spec.stations.map(s => s.x)")
    assert set(st["landmarks"]) == {"face_out", "lip_apex"}
    assert st["points"][0][0] == pytest.approx(0, abs=1e-6) and st["points"][-1][0] == pytest.approx(0, abs=1e-6)


def test_save_writes_the_library_file(page, server):
    page.fill("#holdName", "e2e_copy")
    page.press("#holdName", "Tab")
    page.click("#btnSave")
    path = server["holds"] / "e2e_copy.json"
    for _ in range(100):
        if path.exists():
            break
        time.sleep(0.05)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["name"] == "e2e_copy"
    assert saved["stations"] == _js(page, "store.toSpec().stations")
    assert "\n        [0.0, " in path.read_text(encoding="utf-8")       # one point per line


def test_both_themes_render(page):
    for theme in ("light", "dark"):
        page.evaluate("(t) => { document.documentElement.dataset.theme = t; }", theme)
        page.wait_for_timeout(100)
        bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        color = _js(page, "'#' + view3d.holdMat.color.getHexString()")
        assert bg and color != "#000000", (theme, bg, color)
    light_bg = page.evaluate("(document.documentElement.dataset.theme = 'light', getComputedStyle(document.body).backgroundColor)")
    dark_bg = page.evaluate("(document.documentElement.dataset.theme = 'dark', getComputedStyle(document.body).backgroundColor)")
    assert light_bg != dark_bg


@pytest.mark.slow
def test_build_from_the_editor(page):
    page.evaluate("() => window.holdgen.store.mutate(s => { s.build.voxel = 0.8; }, {commit: true})")
    page.click("#btnBuild")
    page.wait_for_selector("#buildBody a:has-text('Download STL')", timeout=120_000)
    for img in ("overlay.png", "preview.png"):
        loc = page.locator(f"#buildBody img[src$='{img}']")
        loc.wait_for()
        page.wait_for_function("(el) => el.complete && el.naturalWidth > 0", arg=loc.element_handle())
    text = page.text_content("#buildBody")
    assert "watertight yes" in text
    href = page.get_attribute("#buildBody a:has-text('Download STL')", "href")
    r = page.request.get(urljoin(page.url, href))
    assert r.ok and len(r.body()) > 10_000


# ---------------------------------------------------------------- from scratch

def _draw_first_section(pg, x=-30):
    _tool(pg, "toolsFront", "+ Station")
    pg.mouse.click(*_screen(pg, "front", x, 40))
    assert _js(pg, "store.newStation") == x
    for z, y in [(0, 15), (8, 24), (13, 36), (14.5, 45), (11, 51), (6, 50)]:
        pg.mouse.click(*_screen(pg, "section", z, y))
    pg.mouse.click(*_screen(pg, "section", 0.4, 47))       # back on the wall: done
    pg.wait_for_function("() => window.holdgen.store.spec.stations.length === 1")


def test_starts_empty_and_builds_up_from_a_drawn_section(blank):
    assert _js(blank, "store.spec.stations.length") == 0
    assert "Nothing drawn" in _js(blank, "preview.state.hint")
    _draw_first_section(blank)
    st = _js(blank, "store.spec.stations[0]")
    assert st["x"] == -30 and len(st["points"]) == 7
    assert st["points"][0][0] == 0 and st["points"][-1][0] == 0             # roots on the wall
    assert st["landmarks"] == {"lip_apex": 4}                              # highest point
    assert _js(blank, "store.newStation") is None
    blank.wait_for_function("() => (window.holdgen.preview.state.hint || '').includes('second')")  # one station: no request
    _tool(blank, "toolsTop", "+ Station")
    blank.mouse.click(*_screen(blank, "top", 30, 5))
    _wait_preview(blank)
    assert _js(blank, "store.spec.stations.map(s => s.x)") == [-30, 30]
    assert _js(blank, "preview.state.mesh.indices.length / 3") > 1000


def test_a_stale_draft_never_leaves_the_editor_blank(browser, server):
    """A draft saved before the view format changed (closed front loop) blanked every tile."""
    legacy = json.loads((ROOT / "holds" / "ravage_example.json").read_text(encoding="utf-8"))
    fv = legacy["front_view"]
    legacy["front_view"] = {"points": fv["upper"] + fv["lower"][::-1][1:-1]}
    ctx, pg, errors = _open(browser, f"{server['url']}/")
    pg.evaluate("(d) => localStorage.setItem('holdgen.draft.v1', d)", json.dumps(legacy))
    pg.reload()
    pg.wait_for_function("() => window.holdgen && window.holdgen.preview.state.data", timeout=15_000)
    assert _js(pg, "store.spec.stations.length") == 5                  # converted, not discarded
    assert "upper" in _js(pg, "store.spec.front_view")
    assert pg.locator("#toolsFront button").count() > 3
    # and one that can't be read at all starts empty, keeps a copy, and says so
    pg.evaluate("() => localStorage.setItem('holdgen.draft.v1', JSON.stringify({stations: [], front_view: 7}))")
    pg.reload()
    pg.wait_for_function("() => window.holdgen && window.holdgen.preview.state.hint")
    assert _js(pg, "store.spec.stations.length") == 0
    assert pg.evaluate("() => localStorage.getItem('holdgen.draft.v1.unreadable')")
    assert "couldn't be opened" in pg.text_content("#toast")
    ctx.close()
    # the browser logs the server's 422 for the unconvertible draft; anything else is a real error
    assert not [e for e in errors if "status of 422" not in e], errors


def test_escape_cancels_a_new_station(blank):
    _tool(blank, "toolsFront", "+ Station")
    blank.mouse.click(*_screen(blank, "front", 0, 40))
    blank.mouse.click(*_screen(blank, "section", 0, 15))
    blank.keyboard.press("Escape")
    assert _js(blank, "store.newStation") is None
    assert _js(blank, "store.spec.stations.length") == 0


def test_outlines_are_bounded_curves(page):
    # Clear the front view through the inspector, then the Outline button makes a fresh one around the stations.
    page.mouse.click(*_screen(page, "front", *_js(page, "store.spec.front_view.upper[3]")))
    page.locator("#inspector button", has_text="Clear this view").click()
    assert _js(page, "store.spec.front_view") is None
    _tool(page, "toolsFront", "Outline")
    fv = _js(page, "store.spec.front_view")
    assert fv["upper"][0] == fv["lower"][0] and fv["upper"][-1] == fv["lower"][-1]
    xs = _js(page, "store.spec.stations.map(s => s.x)")
    assert fv["upper"][0][0] < min(xs) and fv["upper"][-1][0] > max(xs)

    seq = _js(page, "preview.seq")                                         # drag the left tip: both edges follow
    a = _screen(page, "front", *fv["upper"][0])
    _drag(page, a, (a[0] - 30, a[1] - 10))
    _wait_preview(page, seq)
    fv2 = _js(page, "store.spec.front_view")
    assert fv2["upper"][0] == fv2["lower"][0] and fv2["upper"][0][0] < fv["upper"][0][0]

    u = fv2["upper"]                                                        # double-click the upper edge: a point is added
    page.mouse.dblclick(*_screen(page, "front", u[1][0], u[1][1]))         # on a control point's spot is on the curve
    n = len(_js(page, "store.spec.front_view.upper"))
    assert n == len(u) + 1
    page.keyboard.press("Delete")                                           # the new point is selected; Delete removes it
    assert len(_js(page, "store.spec.front_view.upper")) == len(u)

    end = _js(page, "store.spec.top_view.points.at(-1)")                    # top view ends slide along the wall
    a = _screen(page, "top", *end)
    _drag(page, a, (a[0] + 25, a[1] - 40))
    p2 = _js(page, "store.spec.top_view.points.at(-1)")
    assert p2[1] == 0 and p2[0] > end[0]


def test_reset_clears_everything_and_undo_brings_it_back(page):
    page.click("#btnReset")
    assert _js(page, "store.spec.stations.length") == 5                    # the first click only arms it
    page.click("#btnReset")
    page.wait_for_function("() => window.holdgen.preview.state.hint")
    assert _js(page, "store.spec.stations.length") == 0
    assert _js(page, "store.spec.front_view") is None and _js(page, "store.spec.top_view") is None
    assert _js(page, "view3d.hold") is None                                 # the old hold is gone from 3D
    page.click("#btnUndo")
    _wait_preview(page)
    assert _js(page, "store.spec.stations.length") == 5
