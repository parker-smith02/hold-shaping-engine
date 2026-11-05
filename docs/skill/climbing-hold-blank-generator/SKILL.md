---
name: climbing-hold-blank-generator
description: Use when designing or generating 3D-printable climbing hold blanks (STL) from reference photos, drawn cross-sections or verbal specs, e.g. crimps, edges, incuts for a given wall angle. Works through the hold-shaping-engine repo (holdgen CLI + editor), not bespoke per-hold code.
---

# Climbing hold blank generator

Holds are designed in the **hold-shaping-engine** repo (github.com/parker-smith02/hold-shaping-engine).
The user draws cross-sections (plus loose front/top views) in the editor; the `holdgen` engine lofts them into a
watertight STL that gets printed, hand-sanded, textured, and used as the master for a silicone mold.
**Never write per-hold SDF code.** Everything a hold needs goes in its spec, `holds/<name>.json` (hold-spec/1).

## Setup

Clone the repo (or work in the user's checkout). The repo's `CLAUDE.md` and `docs/HANDOFF.md` are authoritative
for the commands and current status. In short:

```sh
uv sync --extra server --extra dev        # or: pip install -e '.[server,dev]'
(cd web && npm ci && npm run build)       # editor, served by holdgen-server at :8000
holdgen-server                            # http://127.0.0.1:8000 (API docs at /api/docs)
```

## Precedence (don't break these)

1. **Drawn sections are authoritative.** A build matches every drawn station to within the voxel tolerance
   (≈0.15 mm max at 0.3 mm voxels). Never "improve", smooth or re-fit a drawn section.
2. **Front/top views are loose guides.** They shape the hold only between and beyond stations.
3. **Description and notes** shape what the drawings don't capture. Express them as `features`
   (dents and grooves anchored in the front or top view), never as custom code.
4. **No targets in the spec.** Depth, incut and ledge angle are readouts. If the user wants a different depth,
   they change the drawing (or approve the change you propose to it).

## Workflow

1. **Get the spec.** Either the user saved it from the editor (`holds/<name>.json`), or you help them draft it.
   From photos or verbal specs, sketch stations as `[z, y]` points (wall on the left, z out of the wall, y up),
   with landmarks `face_out` and `lip_apex`. Then have the user check and adjust them in the editor;
   the drawing is theirs.
2. **Validate:** `holdgen validate holds/<name>.json`. Fix errors *with* the user; don't guess at their drawing.
3. **Read intent.** Read the spec's `description`, each station's `note` and the pinned `notes`. Add whatever the
   sections don't capture as `features` (e.g. a thumb dent in the front view, a diagonal flute as a groove).
   Don't add stations to fake a diagonal feature; that's what grooves are for.
4. **Build:** `holdgen build holds/<name>.json -o out/<name>` (20–35 s; `--voxel 0.8` for a quick look).
5. **Verify. Look at the images before reporting.**
   - `overlay.png`: drawn (black) vs built (blue) at every station. Stations marked "(cuts screw)" or "(feature)"
     are expected to deviate there.
   - `preview.png`: the shape as a whole.
   - `report.md`: fidelity per station (with notes), readouts (depth, chord incut, incut at wall and near lip,
     ledge angle on the wall, thickness), screw face thickness, and print overhangs.
6. **Report honestly.** Give the size, volume and watertightness, the worst station deviation away from screws and
   features, and the readouts. Flag face thickness under ~12 mm at a screw, and overhangs that need supports.

## House style (user preferences; apply when drafting, never to override a drawing)

- No texture, grain or noise in the STL: the user textures by hand. Smooth contours; subtle asymmetry is fine.
- mm. The back is flat at z = 0. Default wall angle is 45° overhang (`wall_angle_deg`).
- Mount with two countersunk screws (4.8 mm through, 90° countersink ~10 mm) unless asked otherwise.
- Crimps: full depth across the middle ~half, tapering toward the ends; a rounded lip (≈3.5 mm on a 15 mm crimp,
  ≈6.5 mm with a slight bulb on a 25 mm one); a sculpted ledge (scooped low at the wall, hooking toward the lip)
  rather than a flat ramp.
- Print flat-back down; supports where the lip curls past ~50° from vertical.

## When the engine can't express something

Say so, and propose an engine change (in `src/holdgen/`, with tests) rather than a one-off script. Known gaps
are listed in `docs/HANDOFF.md`; for example, tips build ~1 mm blunter than drawn.
