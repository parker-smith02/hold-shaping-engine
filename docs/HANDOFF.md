# Handoff: restructure branch (2026-11-05)

Branch `restructure-monorepo`. It was written in a cloud session whose network policy blocked PyPI and npm,
so several parts have **never run against their real dependencies**. The first job of the next session is
to install everything and run every suite, then fix what breaks.

## How we got here

1. **Earlier sessions** generated holds (Ravage crimp, Joe's) with hand-coded SDF math per hold. That worked,
   but every hold was bespoke code.
2. **Phase 1, engine:** loft drawn cross-sections, with loose front/top views, into an SDF, then mesh it into
   an STL and verify it against the drawing. Tested by rebuilding Ravage v2 from sections extracted from its
   own SDF (`tools/research/ravage_v2/`).
3. **Phase 2, editor:** first built as a single-file claude.ai artifact ("Holdgen Studio", with a JS port of
   the loft). Rejected as the long-term home because of the duplicated geometry kernel, no build from the UI,
   the sandbox constraints, and specs stored outside git.
4. **This branch** restructures the project as engine + FastAPI server + Vite/TypeScript/three.js editor,
   with `holds/` as the git-tracked library.

## Verification status

| part | status |
|---|---|
| Engine (`loft`, `sdf`, `build`, `mesh`, `verify`, `preview`, `fit`, `schema`, `spec`, `pipeline`, CLI) | Fast pytest suite passes (43 tests). Slow builds passed in earlier runs, but haven't been re-run since the latest loft changes (query-time pinning, tip-slope fix). |
| Hypothesis property tests (`tests/test_loft.py`) | Only ran under a local stand-in that feeds random examples without shrinking. **Run under real hypothesis.** |
| FastAPI app (`src/holdgen_server/app.py`) + `tests/test_server.py` | **Never run.** The handler logic was exercised end to end in an equivalent Starlette version (preview, 422/400 mapping, section-at, library CRUD, a real build job, STL download, traversal rejection), then ported to FastAPI. |
| Build jobs (`jobs.py`, spawn process pool, worker-written status) | Ran end to end in the Starlette version. |
| `codegen.py`, `tools/gen_golden.py`, `--check` modes | Run; generated files are committed and current. |
| `web/` unit tests (curves vs golden, edit ops, store) | 23 pass under Node type-stripping with a vitest stand-in. **Run under real vitest.** |
| `web/` typecheck | Clean against stand-in declarations for `three` / `vite/client`. **Run `npm run typecheck` with real `@types/three`.** |
| `web/` in a browser (panes, preview sync, 3D view, build panel, library, import/export) | **Never run.** Ported from the artifact editor, which was exercised in Playwright (drag, insert point, add station, screws, features, landmarks, undo). The 3D view now uses real three.js plus OrbitControls instead of a hand-rolled orbit. |
| `vite build` | **Never run.** |

## Next tasks, in order

1. **Environment.** Network access must be Trusted (or Custom including the package registries). Install:
   `uv pip install -e '.[server,dev]'`, `cd web && npm install`, `python -m playwright install chromium`.
   Commit `uv.lock` (via `uv lock`) and `web/package-lock.json`.
2. **Python:** `pytest` (all of it, including slow). Expect the most fixes in `test_server.py`, since FastAPI
   has never run. Check that `uvicorn[standard]` and the lifespan shutdown of the process pool behave.
3. **Web:** `npm run typecheck`, `npm test`, `npm run build`. Likely spots:
   - `view3d.ts` against the real `@types/three` 0.170 (OrbitControls import path `three/addons/...`).
   - Light intensities under the physically based lighting three.js has used since r155 (the values may be dim or bright).
4. **Run the app** (`holdgen-server` + `npm run dev`) and check in a browser:
   - drag a section point and watch the 3D view and readouts follow (preview should be ~40 ms server side);
   - add a station from the front view (uses `/api/section-at`);
   - save, which writes `holds/<name>.json`;
   - Build STL, which shows overlay.png and preview.png;
   - both themes.
5. **Write `tests/test_e2e.py`** (planned, not written). Playwright (Python) against `create_app(..., web_dist=web/dist)`
   in a uvicorn thread; drive the editor through `window.holdgen` (`{store, preview, panes, view3d}`) plus real
   pointer events. Mark it `@pytest.mark.e2e` (the marker is already registered in pyproject).
6. **CI:** add `.github/workflows/ci.yml`. Python job: install, `codegen --check`, `gen_golden --check`, `pytest`.
   Web job: `npm ci`, typecheck, test, build. e2e job: build web, then `pytest -m e2e`.
7. **SessionStart hook** for cloud sessions (`.claude/settings.json`). It was blocked from being written by the
   agent, so the user adds or approves it. It runs a script that, when `CLAUDE_CODE_REMOTE=true`, does
   `pip install -e '.[server,dev]'` and `npm install` in `web/`.
8. **Skill rewrite.** The user's claude.ai skill `climbing-hold-blank-generator` predates this design (it
   assumes bespoke SDF code per hold). Rewrite it around this repo: the CLI, the verify loop, features from the
   description, and the precedence rules in CLAUDE.md. Propose it with the propose-skills tool; don't write
   skill files directly.

## Known issues and follow-ups

- **Tips** come out slightly blunter than the outline (~1.2 mm at the very points on Ravage). Possible fix: a `tip_sharpness` option.
- **Preview vs build:** the preview mesh is a skin of the same loft, with no SDF smoothing, and its rounded caps are approximated by insetting along normals. The build is exact. The Build panel shows the real result.
- **Build time** is 20–35 s, dominated by per-slice KD-tree queries in `sdf.slice_sdf`. Candidates: vectorize across slices, or numba.
- **Preview payload** is ~1.8 MB of base64 JSON. If localhost latency matters, add a binary endpoint (e.g. `application/octet-stream` with a small header).
- **Diagonal features** (e.g. Ravage's ledge fold) can't come from blending stations along x; that's what grooves are for. More stations don't help; the station-count study showed it.
- **The old artifact editor** (claude.ai artifact "Holdgen Studio") is superseded. Its library holds only `ravage_example`, which is also `holds/ravage_example.json`.

## Reference numbers (Ravage v2 rebuild, `tests/fixtures/ravage_5st_handfit.json`)

- **Section points:** 5 stations at x = −55, −25, −0.1, 25.1, 55.1, about 11 points each.
- **Build:** 157.4 × 60.0 × 21.8 mm, ~84 cm³, watertight.
- **Station deviation** ≤ 0.21 mm, away from screw holes.
- **Surface vs the original v2:** mean 0.14 mm, p95 0.40 mm, max 1.23 mm (at the tip points).
