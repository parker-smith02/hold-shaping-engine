# Handoff: restructure branch (updated 2026-11-05)

Branch `restructure-monorepo`. The first version of this branch was written in a cloud session with no package
registry access. A local session (Windows 11, Python 3.14, Node 24) has since installed every dependency, run
every suite against the real packages, fixed what broke, and worked through the task list below.

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
| Engine + CLI | Full pytest suite passes, slow builds included, on Python 3.14 (Windows); fast suite also passes on 3.12. |
| Hypothesis property tests | Pass under real hypothesis. |
| FastAPI app + `test_server.py` | Pass. Fixed: a bad hold name in `PUT /api/holds/{name}` now returns 400, not 422. |
| Build jobs | Pass, plus `test_jobs.py`. Hardened for Windows (status-file replace/read retries); shutdown now kills a running build; a restart marks interrupted jobs failed. |
| `web/` typecheck, vitest, `vite build` | Pass against the real `@types/three` 0.170 and vitest 2. three.js is split into its own chunk. |
| Editor in a browser | Checked by hand and covered by `tests/test_e2e.py` (Playwright): starting from an empty hold (draw the first section, add a second, preview appears), load + preview, drag a section point (preview follows, ~85 ms round trip), undo, add a station from the front view, outlines (default around the stations, drag a tip or wall end, double-click to add, Delete to remove), Reset + undo, save, both themes, build from the editor down to the STL download. |
| API robustness | `tests/test_server_robust.py` fuzzes validate/preview/section-at with plausible and arbitrary specs (~70% reach the loft): no 5xx. Found and fixed a 500 in section-at on near-flat sections. |
| CI (`.github/workflows/ci.yml`) | Written. **Not yet run on GitHub**: it triggers on PRs and pushes to `main`, and this branch has no open PR (PR #1 is already merged). |
| SessionStart hook | `.claude/settings.json` → `scripts/session-start.sh`. Syntax and the local no-op path were checked. **The cloud install path hasn't run yet.** |
| Skill rewrite | Draft at `docs/skill/climbing-hold-blank-generator/SKILL.md`. Needs the user to upload it on claude.ai; there was no propose-skills tool in the session. |

Other changes from the local session:

- **UTF-8 and LF everywhere.** All text I/O is explicit UTF-8, and generators write LF. `.gitattributes` keeps LF in
  the working tree so the `--check` modes are byte-stable on Windows.
- **Lint.** ruff rules are pinned in `pyproject.toml` (pyflakes, import order, syntax-level E) and the tree is clean.
- **Locks.** `uv.lock` and `web/package-lock.json` are committed. `tests/test_codegen.py` runs both stale-file checks.
- **Feature flags in reports.** A station is flagged "crosses feature k" where a dent or groove moves the surface by
  more than 0.05 mm. On `ravage_example` this explains the 0.69 mm deviation at x = 25.1 (the diagonal groove).
  The editor's "worst deviation" skips those stations, as it already skipped screw cuts.

## Next tasks

1. **Run CI**: open a PR from this branch to `main` and fix anything Linux-specific.
2. **Upload the skill draft** on claude.ai, replacing the old `climbing-hold-blank-generator`.
3. **Confirm the SessionStart hook** in a cloud session (deps install, venv on PATH).

## Spec change: open outline curves

`front_view` is `{upper, lower, strength}`: two open curves from the left tip to the right tip, sharing the tips
(corners in the loft). `top_view.points` runs from the wall to the wall (first and last z = 0). Old closed loops
still load (a before-validator splits them at the tips); `holds/` and the fixtures are stored in the new form.
The editor starts empty (no starter shape), never sends a spec with fewer than two stations, and has a Reset
button (undoable) in place of New.

## Known issues and follow-ups

- **Tips** come out slightly blunter than the outline (~1.2 mm at the very points on Ravage). Possible fix: a `tip_sharpness` option.
- **Preview vs build:** the preview mesh is a skin of the same loft, with no SDF smoothing, and its rounded caps are approximated by insetting along normals. The build is exact. The Build panel shows the real result.
- **Build time** is 20–35 s, dominated by per-slice KD-tree queries in `sdf.slice_sdf`. Candidates: vectorize across slices, or numba.
- **Preview payload** is ~1.8 MB of base64 JSON. If localhost latency matters, add a binary endpoint (e.g. `application/octet-stream` with a small header).
- **Diagonal features** (e.g. Ravage's ledge fold) can't come from blending stations along x; that's what grooves are for. More stations don't help; the station-count study showed it.
- **Deprecation warnings:** Starlette warns that its `TestClient` wants `httpx2`, and scikit-image's marching cubes sets `.shape` on arrays (deprecated in NumPy 2.5). Neither breaks anything yet.
- **The old artifact editor** (claude.ai artifact "Holdgen Studio") is superseded. Its library holds only `ravage_example`, which is also `holds/ravage_example.json`.

## Reference numbers (Ravage v2 rebuild, `tests/fixtures/ravage_5st_handfit.json`)

- **Section points:** 5 stations at x = −55, −25, −0.1, 25.1, 55.1, about 11 points each.
- **Build:** 157.4 × 60.0 × 21.8 mm, ~84 cm³, watertight.
- **Station deviation** ≤ 0.21 mm, away from screw holes.
- **Surface vs the original v2:** mean 0.14 mm, p95 0.40 mm, max 1.23 mm (at the tip points).
