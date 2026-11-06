# Handoff (updated 2026-11-05)

Read `CLAUDE.md` first (invariants, frame, commands). This file is the current state, what has been verified,
the gotchas that cost time, and where to pick up.

## Where things stand

| | |
|---|---|
| `main` | Has everything up to PR #2 (restructure, real-dependency fixes, e2e tests, CI, SessionStart hook, skill draft). |
| PR #3 `restructure-monorepo` (open) | One commit: `status.json` write race fix (CI on `main` caught it on Python 3.11). |
| Branch `editor-from-scratch` (pushed, **no PR yet**) | Cut from `restructure-monorepo`, so it contains #3's commit plus 4 commits: README venv note; open-curve views + never-5xx server; from-scratch editor + Reset; stale-draft/old-file migration. Merge #3 first, then PR this one (its diff then shows only the new work). |
| Verified | 82 pytest (slow builds + 11 browser tests), 31 vitest, typecheck, `vite build`, ruff, `codegen --check`, `gen_golden --check`: all green locally (Windows 11, Python 3.14, Node 24). CI is green on PRs; this branch hasn't had its own CI run. |

## What the editor does now

- **Starts empty** (or your last draft). No starter shape. `+ Station` on an empty hold puts the section pane in
  draw mode for that x (`store.newStation`; the front/top panes mark it); the station joins the spec only when its
  section is finished (click the wall, up the face, over the lip, the wall again; Esc cancels). First station gets
  `lip_apex` (highest point) only. Later stations are cut from the loft (`/api/section-at`) or copied from the nearest.
- **No preview request with fewer than two stations** (`previewHint` in `main.ts`, `PreviewState.hint`); the 3D view
  clears and each pane shows instructions. This is what stopped the editor from sending specs the server rejects.
- **Reset** (armed double-click) replaces New: empty hold, clears the saved draft, undoable.
- **Outlines are open curves, created by the Outline button** around the stations (`defaultFrontView` /
  `defaultTopView` in `spec/edit.ts`). Front = `upper` + `lower` edges sharing two tips (a tip moves both edges);
  top = wall to wall (ends slide along z = 0). Interior points stay between the ends; double-click a curve adds a
  point on it; Delete removes interior points; the inspector explains each. Clearing a view is in the inspector.
- **Old data keeps loading.** `POST /api/migrate` and `GET /api/holds/<name>` return specs in the current shape
  (the before-validators in `schema.py` split old closed loops at the tips). Drafts and Import go through
  `web/src/spec/load.ts`. A draft that still can't open is set aside under `localStorage["holdgen.draft.v1.unreadable"]`
  and the editor starts empty with a toast; a failed `main()` is shown on the page, not just the console.
  Migration stays in Python (one spec definition); don't port it to TypeScript.

## Spec format change (hold-spec/1, still `/1`)

`front_view`: `{upper, lower, strength}`, each edge an open `[x, y]` curve from the left tip to the right tip, tips
shared (corners in the loft). `top_view`: `{points, strength, corners}` from the wall to the wall (first and last
z = 0). New checks: `front_view.tips|direction|outside_tips`, `top_view.ends_off_wall|direction`. `holds/` and the
fixtures are rewritten in the new form. Front-edge points have no per-point `corners` any more (the tips are the
corners); add them to the schema if wanted.

## Environment notes (Windows 11, PowerShell/Git Bash)

- **Activate the venv** (`.venv\Scripts\Activate.ps1`) or use `uv run ...`; `holdgen`/`holdgen-server` live in `.venv`.
- **After any `uv sync`, run `python -m playwright install chromium`**: the lock pins a Playwright whose browser
  build may be missing, and e2e fails with "Executable doesn't exist".
- **No git identity is configured on this machine.** Commits so far set `GIT_AUTHOR_*`/`GIT_COMMITTER_*` per command
  to `Parker Smith <92767649+parker-smith02@users.noreply.github.com>`. `gh` is logged in as `parker-smith02`.
- `.claude/launch.json` (API :8000, Vite :5173) uses `.venv/Scripts/holdgen-server.exe`: Windows-only path.
- All text I/O is explicit UTF-8 with LF (`.gitattributes`); generators write LF so the `--check` modes are
  byte-stable. Don't use bare `read_text()`/`open()`.
- Bash heredocs choke on backticks and `\n` inside TS/Python source; write scripts to files instead of
  inlining them in a shell command.
- uv's managed Python 3.11 is broken here; CI covers 3.11 and 3.13, local covers 3.14 (and 3.12 via a scratch venv).

## Testing notes

- **e2e (`tests/test_e2e.py`)** needs `web/dist` (`npm run build`). Use the `page` fixture (opens
  `?hold=ravage_example`) or `blank` (first-time visitor). Each test gets a fresh browser context, which is why
  saved-draft bugs went unseen until a real browser hit one; `test_a_stale_draft_never_leaves_the_editor_blank` now
  covers it. Anything that touches startup, `localStorage` or the spec shape needs an e2e test.
- `window.holdgen = {store, preview, panes, view3d}` is the debugging/e2e handle; panes expose `toScreen(x, y)`.
- After a pointer edit, wait on `preview.seq` advancing (`_wait_preview(pg, seq)`); don't assert straight away
  (the preview is debounced 40 ms).
- `tests/test_server_robust.py` fuzzes validate/preview/section-at (plausible + arbitrary specs, ~70% reach the loft)
  and asserts no 5xx. `/api/preview` and `/api/section-at` turn any engine exception into a 422 with a message.
- `python tools/ui_walkthrough.py . out/walkthrough` drives the built editor from empty and saves a screenshot per
  step: the quickest way to eyeball layout, theming and empty states.
- Slow suite ~100 s. Flaky-test history: the job-status race (fixed, with a threaded stress test). The one-off
  Windows failure of that stress test on its first run is unexplained (passed 18/18 afterwards).

## Not yet done / not yet verified

1. **PRs:** merge #3, then open a PR for `editor-from-scratch` and watch CI (Linux, Python 3.11/3.13).
2. **Skill:** `docs/skill/climbing-hold-blank-generator/SKILL.md` is a draft; upload it on claude.ai to replace the
   old skill (no tool for that in the session).
3. **SessionStart hook** (`scripts/session-start.sh`): only the local no-op path was run; confirm the install path in a
   cloud session.
4. The user has run the editor in Chrome against `vite dev` (found the stale-draft blank screen). Their next feature
   requests were not specified when this was written: ask.

## Candidate follow-ups (none started)

- **Editor:** first station only gets `lip_apex` (add `face_out` or let users name landmarks as they draw);
  front-edge per-point corners; a way to drag a whole station or section from the outline panes; seeing the
  neighbour stations ghosted while drawing the first section of a new x; keyboard/undo coverage for the draw flow
  (cancel by tool switch is untested); `Outline` on an existing view only re-selects (maybe offer "reset outline").
- **Engine:** tips build ~1.2 mm blunter than drawn (a `tip_sharpness` option); build time 20-35 s, dominated by
  per-slice KD-tree queries in `sdf.slice_sdf` (vectorize or numba); preview payload ~1.8 MB base64 JSON (binary
  endpoint); diagonal features can't come from blending stations along x (use grooves; the station-count study
  showed more stations don't help).
- **Housekeeping:** Starlette's `TestClient` wants `httpx2`; scikit-image marching cubes sets `.shape` (deprecated
  in NumPy 2.5); the old claude.ai artifact "Holdgen Studio" is superseded (its library held only `ravage_example`).

## How we got here

1. Earlier sessions generated holds (Ravage crimp, Joe's) with hand-coded SDF math per hold.
2. Phase 1, engine: loft drawn cross-sections, with loose front/top views, into an SDF, mesh it, verify against the
   drawing (tested on Ravage v2 rebuilt from sections extracted from its own SDF, `tools/research/ravage_v2/`).
3. Phase 2, editor: first a single-file claude.ai artifact with a JS port of the loft; rejected (duplicated kernel,
   no build from the UI, sandbox limits, specs outside git).
4. Restructure into engine + FastAPI server + Vite/TypeScript/three.js editor with `holds/` as the library (PR #1),
   made to run against real dependencies (PR #2), then the open-curve views and from-scratch editor (this branch).

## Reference numbers (Ravage v2 rebuild, `tests/fixtures/ravage_5st_handfit.json`)

- 5 stations at x = −55, −25, −0.1, 25.1, 55.1, about 11 points each; views now stored as upper/lower + top curve.
- Build: 157.4 × 60.0 × 21.8 mm, ~84 cm³, watertight.
- Station deviation ≤ 0.21 mm away from screw holes and features. On `ravage_example` the groove explains 0.69 mm at x = 25.1.
- Surface vs the original v2: mean 0.14 mm, p95 0.40 mm, max 1.23 mm (at the tip points).
