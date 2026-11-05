"""Golden spline outputs from holdgen.curves for the TypeScript port (web/src/geometry/curves.test.ts).

    python tools/gen_golden.py           # rewrite web/src/geometry/curves.golden.json
    python tools/gen_golden.py --check   # exit 1 if stale (CI; also run by tests/test_codegen.py)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from holdgen import curves  # noqa: E402

OUT = ROOT / "web" / "src" / "geometry" / "curves.golden.json"

SECTION = [[0, 15.9], [5.4, 20.1], [11.2, 29.8], [16.4, 42.5], [19.8, 55.2], [21.9, 64.3], [20.6, 71.0],
           [17.1, 73.6], [12.8, 70.2], [7.9, 63.1], [3.6, 59.4], [0, 58.0]]
OUTLINE = [[-80, 50], [-55, 68], [-20, 74], [20, 73], [55, 66], [82, 49], [60, 26], [20, 14], [-25, 15], [-60, 27]]


def cases() -> list[dict]:
    out = []
    for name, pts, corners, step in (
        ("section", SECTION, [], 0.5),
        ("section_corners", SECTION, [3, 8], 0.5),
        ("short", [[0, 0], [5, 10], [0, 12]], [], 0.25),
    ):
        dense, idx = curves.eval_open(pts, corners, step=step)
        out.append({"name": name, "kind": "open", "points": pts, "corners": corners, "step": step,
                    "dense": dense.tolist(), "idx": idx.tolist()})
    for name, corners in (("outline", []), ("outline_corners", [0, 5])):
        dense = curves.eval_closed(OUTLINE, corners, step=1.0)
        out.append({"name": name, "kind": "closed", "points": OUTLINE, "corners": corners, "step": 1.0, "dense": dense.tolist()})
    return out


def render() -> str:
    return json.dumps({"generated_by": "tools/gen_golden.py", "cases": cases()}, separators=(",", ":")) + "\n"


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        sys.exit(0 if OUT.exists() and OUT.read_text(encoding="utf-8") == text else 1)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
