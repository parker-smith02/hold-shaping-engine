# hold-shaping-engine

Climbing-hold blank designer. The user draws cross-sections (plus loose front/top views) in a web
editor; the engine lofts them into a watertight STL that is 3D printed, sanded, textured and used as
the master for a silicone mold. The user is an experienced software engineer: work at that level, and
don't simplify architecture to fit what happens to be installed. If a dependency is missing, install it.

Current status, what has and hasn't been verified, and the next tasks: **docs/HANDOFF.md** (read it first).

## Invariants (don't break these)

- **Sections are authoritative.** A built hold matches every drawn station within the voxel tolerance
  (≈0.15 mm max / ≈0.01 mm mean at 0.3 mm voxels). Never "improve" a drawn section.
- **Views are loose guides.** Front/top view corrections are exactly zero at every station (pinned at
  query time in `Loft._pinned_residual`) and only shape the hold between and beyond stations.
  `tests/test_loft.py::test_views_never_move_a_station` guards this.
- **No constraints in specs.** Depth, incut, etc. are readouts (information), never targets.
- **One geometry kernel.** All lofting lives in `src/holdgen/loft.py`. The editor gets preview geometry from
  `POST /api/preview`; the client only evaluates splines for drawing (`web/src/geometry/curves.ts`,
  locked to Python by `curves.golden.json`). Don't port lofting to TypeScript.
- **One spec definition.** `src/holdgen/schema.py` (pydantic) is the source of truth for hold-spec/1.
  `schema/hold-spec.schema.json` and `web/src/api/types.gen.ts` are generated; never hand-edit them.

## Frame and units

mm. x along the hold, y up the wall, z out of the wall; the back is z = 0. Section points are `[z, y]`
(drawn with the wall on the left). Front view points `[x, y]`; top view `[x, z]`.

## Commands

```sh
uv venv && uv pip install -e '.[server,dev]'        # Python 3.11+
(cd web && npm install)
python -m playwright install chromium                # for e2e tests

pytest -m "not slow"                                 # fast suite (~5 s)
pytest                                               # + full SDF builds (~1-2 min)
(cd web && npm test && npm run typecheck && npm run build)

python -m holdgen_server.codegen                     # regenerate types.gen.ts + JSON Schema after model changes
python tools/gen_golden.py                           # regenerate curves.golden.json after curves.py changes

holdgen-server                                       # API :8000 (docs at /api/docs); serves web/dist if built
(cd web && npm run dev)                              # editor :5173, proxies /api -> :8000
holdgen build holds/<name>.json -o out/<name>        # STL + report.md + overlay.png + preview.png
```

## Building a hold for the user

1. `holdgen validate holds/<name>.json`; fix errors with the user (don't guess at their drawing).
2. Read the spec's `description`, station `note`s and pinned `notes`. Express anything the sections don't
   capture as `features` entries (dents/grooves anchored in the front or top view), never as custom code.
3. `holdgen build ...`, then look at `overlay.png` (drawn vs built at every station) and `preview.png`,
   and read `report.md` (fidelity, readouts, screw face thickness, print overhangs).
4. Report deviations honestly; stations that cross a screw hole or a feature are expected to deviate.

## Conventions

- Tests: pytest + hypothesis for invariants; slow builds marked `@pytest.mark.slow`; vitest for `web/`.
- `holds/*.json` are written by `HoldStore` (one point per line) so diffs stay readable.
- Commit on a branch; the default branch is `main`.
