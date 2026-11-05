"""holdgen command line.

    holdgen build holds/x.json -o out/x    # STL + report + overlay/preview/spec-sheet images
    holdgen validate holds/*.json          # schema + semantic checks, non-zero exit on errors
    holdgen sheet holds/x.json -o out/x    # spec sheet only (fast)
    holdgen schema                         # print the hold-spec/1 JSON Schema
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import loft as loft_mod, pipeline, render, schema, spec as spec_mod


def _load_raw(path):
    with open(path) as f:
        return json.load(f)


def cmd_build(a) -> int:
    try:
        spec = spec_mod.load(a.spec)
    except spec_mod.SpecError as e:
        for i in e.issues:
            print(f"{i.level}: {i.message}", file=sys.stderr)
        return 2
    if a.voxel:
        spec["build"]["voxel"] = a.voxel
    out = a.out or os.path.join("out", spec["name"])
    summary = pipeline.build_to_dir(spec, out, previews=not a.no_preview, log=lambda m: print(m, file=sys.stderr))
    print(open(os.path.join(out, "report.md")).read())
    return 0 if summary["mesh"]["watertight"] else 1


def cmd_validate(a) -> int:
    bad = 0
    for p in a.specs:
        model, issues = schema.validate(_load_raw(p))
        errs = [i for i in issues if i.level == "error"]
        bad += bool(errs) or model is None
        print(f"{p}: {'ok' if not errs else f'{len(errs)} error(s)'}"
              + (f", {len(issues) - len(errs)} warning(s)" if len(issues) > len(errs) else ""))
        for i in issues:
            print(f"  {i.level}: {i.message}")
    return 1 if bad else 0


def cmd_sheet(a) -> int:
    spec = spec_mod.load(a.spec)
    out = a.out or os.path.join("out", spec["name"])
    os.makedirs(out, exist_ok=True)
    render.spec_sheet(spec, loft_mod.Loft(spec), os.path.join(out, "spec_sheet.png"))
    return 0


def cmd_schema(a) -> int:
    print(json.dumps(schema.json_schema(), indent=2))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="holdgen")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build an STL and report from a spec")
    b.add_argument("spec")
    b.add_argument("-o", "--out")
    b.add_argument("--voxel", type=float)
    b.add_argument("--no-preview", action="store_true")
    v = sub.add_parser("validate", help="check specs")
    v.add_argument("specs", nargs="+")
    s = sub.add_parser("sheet", help="render the spec sheet only")
    s.add_argument("spec")
    s.add_argument("-o", "--out")
    sub.add_parser("schema", help="print the JSON Schema")
    a = p.parse_args(argv)
    return {"build": cmd_build, "validate": cmd_validate, "sheet": cmd_sheet, "schema": cmd_schema}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
