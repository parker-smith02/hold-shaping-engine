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

```sh
holdgen-server                          # API on :8000 (serves web/dist if built)
cd web && npm run dev                   # editor on :5173, proxies /api to :8000

holdgen validate holds/*.json
holdgen build holds/ravage_example.json -o out/ravage   # STL + report.md + overlay/preview/spec-sheet PNGs
```

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
