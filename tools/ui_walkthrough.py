"""Drive the built editor from an empty hold with real pointer events and save a screenshot per step.

    (cd web && npm run build)
    python tools/ui_walkthrough.py . out/walkthrough      # then look at out/walkthrough/*.png

For eyeballing layout, theming and empty states; the assertions live in tests/test_e2e.py."""
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "out/walkthrough")
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "src"))
from holdgen_server.app import create_app  # noqa: E402

tmp = Path(tempfile.mkdtemp())
shutil.copytree(ROOT / "holds", tmp / "holds")
app = create_app(tmp / "holds", tmp / "builds", ROOT / "web" / "dist")
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
threading.Thread(target=srv.run, daemon=True).start()
while not srv.started:
    time.sleep(0.05)

errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    pg.goto(f"http://127.0.0.1:{port}/")
    pg.wait_for_function("() => window.holdgen && window.holdgen.preview.state.hint")

    def js(expr, arg=None):
        return pg.evaluate(f"(arg) => {{ const {{store, preview, panes, view3d}} = window.holdgen; return {expr}; }}", arg)

    def scr(pane, x, y):
        return tuple(js("""(() => { const p = panes[arg.pane]; const s = p.toScreen(arg.x, arg.y);
                         const r = p.cv.getBoundingClientRect(); return [r.left + s[0], r.top + s[1]]; })()""",
                        {"pane": pane, "x": x, "y": y}))

    def shot(name):
        pg.wait_for_timeout(250)
        pg.screenshot(path=str(OUT / f"{name}.png"))
        print(name, "| stations:", js("store.spec.stations.map(s => [s.x, s.points.length, Object.keys(s.landmarks)])"),
              "| hint:", js("preview.state.hint"), "| err:", js("preview.state.error"))

    shot("01_empty")
    pg.locator("#toolsFront button", has_text="+ Station").click()
    pg.mouse.click(*scr("front", -30, 40))
    shot("02_drawing_mode")
    for z, y in [(0, 15), (8, 24), (13, 36), (14.5, 45), (11, 51), (6, 50)]:
        pg.mouse.click(*scr("section", z, y))
    pg.mouse.move(*scr("section", 2, 48))
    shot("03_mid_draw")
    pg.mouse.click(*scr("section", 0.4, 47))        # back on the wall: finish
    shot("04_first_station")
    pg.locator("#toolsTop button", has_text="+ Station").click()
    pg.mouse.click(*scr("top", 30, 5))
    pg.wait_for_function("() => window.holdgen.preview.state.data && !window.holdgen.preview.state.pending")
    shot("05_two_stations_preview")
    pg.locator("#toolsFront button", has_text="Outline").click()
    pg.locator("#toolsTop button", has_text="Outline").click()
    pg.wait_for_timeout(300)
    shot("06_outlines")
    tip = js("store.spec.front_view.upper[0]")
    a = scr("front", *tip)
    pg.mouse.move(*a); pg.mouse.down(); pg.mouse.move(a[0] - 40, a[1] - 15, steps=6); pg.mouse.up()
    end = js("store.spec.top_view.points.at(-1)")
    a = scr("top", *end)
    pg.mouse.move(*a); pg.mouse.down(); pg.mouse.move(a[0] + 40, a[1] - 30, steps=6); pg.mouse.up()
    up = js("store.spec.front_view.upper")
    mid = [(up[1][0] + up[2][0]) / 2, None]
    dense_y = js("(() => { const u = store.spec.front_view.upper; return (u[1][1] + u[2][1]) / 2; })()")
    pg.mouse.dblclick(*scr("front", mid[0], dense_y))
    pg.wait_for_function("() => !window.holdgen.preview.state.pending")
    shot("07_dragged_tip_end_and_inserted")
    print("front:", js("store.spec.front_view"), "\ntop:", js("store.spec.top_view.points"))
    pg.click("#btnReset")
    pg.click("#btnReset")
    pg.wait_for_function("() => window.holdgen.preview.state.hint")
    shot("08_after_reset")
    pg.click("#btnUndo")
    pg.wait_for_function("() => window.holdgen.preview.state.data && !window.holdgen.preview.state.pending")
    shot("09_undo_reset")
    pg.emulate_media(color_scheme="dark")
    pg.click("#btnReset")
    pg.click("#btnReset")
    shot("10_reset_dark")
    b.close()
srv.should_exit = True
print("page errors:", [e for e in errors if "GPU stall" not in e] or "none")
