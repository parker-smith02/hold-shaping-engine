# hold-shaping-engine

Design climbing-hold blanks by drawing cross-sections, then loft them into a watertight STL for 3D printing
(print → sand/texture → silicone mold → cast holds).

- **Sections are authoritative.** Each drawn station is matched within the voxel tolerance (≈0.15 mm at 0.3 mm voxels).
- **Front and top views are loose guides.** They shape the hold between stations and taper the tips, and are
  pinned to zero at every station, so they can never move a drawn section.
- **One geometry kernel.** The editor's live preview and the STL build both use `holdgen.loft`.

## Layout

| path | what |
|---|---|
| `src/holdgen/` | engine: `schema` (hold-spec/1 pydantic model), `loft`, `sdf`, `features`, `build`, `mesh`, `verify`, `preview`, `fit`, `pipeline`, CLI |
| `src/holdgen_server/` | FastAPI app for the editor: preview, validation, hold library, build jobs, TS codegen |
| `web/` | Holdgen Studio: Vite + TypeScript + three.js editor |
| `holds/` | the hold library, one `<name>.json` per hold (git-tracked) |
| `schema/hold-spec.schema.json` | generated JSON Schema |
| `tests/` | pytest: unit, property (hypothesis), golden build regression, API, store |
| `tools/` | `gen_golden.py` (TS↔Python spline fixture), `research/ravage_v2/` (reference-hold extraction study) |

## Setup

```sh
uv venv && uv pip install -e '.[server,dev]'      # or: pip install -e '.[server,dev]'
cd web && npm install && cd ..
```

## Use

`holdgen` and `holdgen-server` are installed into the project's `.venv`, so activate it first in each new
terminal (or prefix commands with `uv run`, e.g. `uv run holdgen-server`):

```sh
.venv\Scripts\Activate.ps1             # Windows PowerShell
source .venv/bin/activate               # macOS / Linux / Git Bash: .venv/Scripts/activate
```

```sh
(cd web && npm run build)               # once, so the server can serve the editor at :8000
holdgen-server                          # API on :8000 (serves web/dist if built)
cd web && npm run dev                   # or: live-reload editor on :5173, proxies /api to :8000

holdgen validate holds/*.json
holdgen build holds/ravage_example.json -o out/ravage   # STL + report.md + overlay/preview/spec-sheet PNGs
```

## Editor workflow

1. The editor opens empty. In the front or top view pick **+ Station** and click where the first section goes;
   draw it in the section pane (click the wall, up the face, over the lip, back to the wall). Add a second station
   and the 3D preview appears.
2. Optionally add **Outline** in the front and top views: loose guides that shape the hold *between* stations and
   toward the tips (drag the square tips/ends, drag points, double-click a curve to add a point). They never move a
   drawn station.
3. Add screws, dents/grooves and notes, **Save** to `holds/<name>.json`, then **Build STL**. **Reset** clears to an
   empty hold (undoable).

## Tests

```sh
pytest -m "not slow"                    # fast suite
pytest                                  # + full SDF builds (Ravage baseline, edge cases)
cd web && npm test && npm run typecheck
python -m holdgen_server.codegen --check && python tools/gen_golden.py --check
```

Generated files (`web/src/api/types.gen.ts`, `schema/hold-spec.schema.json`, `web/src/geometry/curves.golden.json`)
come from the pydantic models and `holdgen.curves`; regenerate with `python -m holdgen_server.codegen` and
`python tools/gen_golden.py`. A test fails if they are stale.

The spec format is documented in the model itself: `src/holdgen/schema.py`.
