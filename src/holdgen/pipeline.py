"""Full build: spec -> STL + verification report + images, written to one directory.

Shared by the CLI (`holdgen build`) and the server's build jobs.
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable

from . import build as build_mod, mesh, render, verify

OUTPUT_FILES = ("hold.stl", "report.md", "report.json", "overlay.png", "spec_sheet.png", "preview.png")


def report_md(spec: dict, chk: dict, rep: dict, screws: list, elapsed: float) -> str:
    L = [f"# {spec['name']}\n"]
    if spec.get("description"):
        L.append(f"> {spec['description']}\n")
    L.append(f"Built in {elapsed:.0f} s at {spec['build']['voxel']} mm voxels. "
             f"Size {chk['size_mm'][0]} x {chk['size_mm'][1]} x {chk['size_mm'][2]} mm, "
             f"volume {chk['volume_cm3']} cm³, {chk['triangles']:,} triangles, "
             f"watertight: {'yes' if chk['watertight'] else 'NO'}.\n")
    L.append("## Fidelity at stations (drawn spline vs built mesh)\n")
    L.append("| x | max dev | mean dev | p95 | note |\n|---|---|---|---|---|")
    feats = spec.get("features", [])
    for s in rep["stations"]:
        d = s["deviation_mm"]
        note = ["cuts a screw hole"] if s["cuts_screw"] else []
        for k in s["features"]:
            f = feats[k]
            note.append(f"crosses feature {k} ({f['type']}: {f['note']})" if f.get("note")
                        else f"crosses feature {k} ({f['type']})")
        L.append(f"| {s['x']:g} | {d['max']:.2f} | {d['mean']:.3f} | {d['p95']:.2f} | {'; '.join(note)} |")
    L.append("\nStations that cut a screw hole or cross a feature are expected to deviate there.")
    L.append("\n## Readouts (information only, not targets)\n")
    L.append(f"Wall angle {spec['wall_angle_deg']}°. 'Ledge on wall' = degrees below horizontal when hung.\n")
    L.append("| x | where | depth | chord incut | incut at wall | incut near lip | ledge on wall | thickness |")
    L.append("|---|---|---|---|---|---|---|---|")
    rows = [(s["x"], "station", s["readouts"]) for s in rep["stations"]] + \
           [(m["x"], "between", m["readouts"]) for m in rep["between"]]
    for x, w, r in sorted(rows, key=lambda t: t[0]):
        L.append(f"| {x:g} | {w} | {r['depth']} | {r['chord_incut']}° | {r['incut_at_wall']}° | "
                 f"{r['incut_near_lip']}° | {r['ledge_below_horizontal_on_wall']}° | {r['thickness']} |")
    L.append("\n## Mounting\n")
    for s in screws:
        warn = f" - {s['warning']}" if "warning" in s else (" - thin, aim for > 12 mm" if s["face_thickness"] < 12 else "")
        L.append(f"- screw at ({s['x']}, {s['y']}): face thickness {s['face_thickness']} mm{warn}")
    o = rep["overhangs"]
    L.append("\n## Printing (flat back down)\n")
    if o["area_mm2"] > 0:
        L.append(f"- {o['area_mm2']:.0f} mm² of surface overhangs more than {o['limit_deg']}° from vertical "
                 f"(max {o['max_deg']}°, x {o['x_range'][0]} to {o['x_range'][1]}); light supports there.")
    else:
        L.append(f"- No overhangs beyond {o['limit_deg']}° from vertical.")
    return "\n".join(L) + "\n"


def build_to_dir(spec: dict, out_dir: str, *, previews: bool = True,
                 log: Callable[[str], None] = lambda m: None) -> dict:
    """Build `spec` (engine dict from spec.normalize) into out_dir. Returns the report.json content."""
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    log(f"building {spec['name']}")
    S, axes, L, screws = build_mod.build(spec, log=log)
    V, T = mesh.from_sdf(S, axes)
    chk = mesh.check(V, T)
    mesh.write_stl(os.path.join(out_dir, "hold.stl"), V, T, header=f"{spec['name']} (holdgen), units mm")
    log(f"  mesh: {chk['triangles']:,} tris, watertight={chk['watertight']}  {time.time() - t0:.1f}s")
    rep = verify.run(spec, L, V, T)
    elapsed = time.time() - t0
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(report_md(spec, chk, rep, screws, elapsed))
    summary = {
        "name": spec["name"], "elapsed_s": round(elapsed, 1), "voxel": spec["build"]["voxel"],
        "mesh": chk, "screws": screws, "overhangs": rep["overhangs"],
        "stations": [{k: v for k, v in s.items() if k != "segments"} for s in rep["stations"]],
        "between": [{"x": m["x"], "readouts": m["readouts"]} for m in rep["between"]],
    }
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    render.overlay(spec, L, rep, os.path.join(out_dir, "overlay.png"))
    render.spec_sheet(spec, L, os.path.join(out_dir, "spec_sheet.png"))
    if previews:
        Vc, Tc = mesh.from_sdf(S, axes, step=2)
        render.preview_sheet(Vc, Tc, os.path.join(out_dir, "preview.png"), title=spec["name"])
    log(f"done in {time.time() - t0:.1f}s -> {out_dir}")
    return summary
