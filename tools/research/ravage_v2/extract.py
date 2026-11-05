"""Build hold-spec/1 files from the original Ravage v2 generator output.

Slices the reference SDF at chosen stations, fits spline control points to each
section (like a person placing points in the editor), labels landmarks, and traces
loose front and top views. Screws are added back as mounting entries.

    python3 extract.py REF_DIR OUT_SPEC.json x1 x2 x3 ... [--views-strength 0.5] [--no-views]
"""
import argparse
import json
import os
import sys

import numpy as np
from skimage.measure import find_contours
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "src"))
from holdgen import curves  # noqa: E402

TOL = 0.04   # mm, max distance of the extracted contour from the fitted spline


def section_contour(S, xs, ys, zs, x):
    i = int(np.argmin(np.abs(xs - x)))
    vox = float(xs[1] - xs[0])
    cs = find_contours(S[i], 0.0)                     # rows = y index, cols = z index
    c = max(cs, key=len)
    P = np.stack([zs[0] + c[:, 1] * vox, ys[0] + c[:, 0] * vox], 1)   # [z, y]
    if np.allclose(P[0], P[-1]):
        P = P[:-1]
    off = P[:, 0] > 0.03                              # drop the flat back
    # rotate so the kept chain is contiguous
    k = np.nonzero(~off)[0]
    start = (k[-1] + 1) % len(P) if len(k) else 0
    P, off = np.roll(P, -start, 0), np.roll(off, -start)
    P = P[off]
    if P[0, 1] > P[-1, 1]:
        P = P[::-1]
    P[0, 0] = 0.0
    P[-1, 0] = 0.0
    return float(xs[i]), P


def fit_controls(P, TOL=TOL):
    must = {0, len(P) - 1, int(np.argmax(P[:, 1])), int(np.argmax(P[:, 0]))}
    sel = sorted(must)
    for _ in range(80):
        dense, _ = curves.eval_open(P[sel])
        d, _ = cKDTree(dense).query(P)
        j = int(np.argmax(d))
        if d[j] < TOL:
            break
        sel = sorted(set(sel) | {j})
    ctrl = P[sel]
    lm = {"face_out": sel.index(int(np.argmax(P[:, 0]))), "lip_apex": sel.index(int(np.argmax(P[:, 1])))}
    return np.round(ctrl, 3), lm, float(d.max())


def front_outline(S, xs, ys, n=30):
    inside = (S < 0).any(2)                            # (nx, ny)
    cols = np.nonzero(inside.any(1))[0]
    lo = np.array([ys[np.nonzero(inside[i])[0].min()] for i in cols])
    hi = np.array([ys[np.nonzero(inside[i])[0].max()] for i in cols])
    x = xs[cols]
    ring = np.vstack([np.stack([x, hi], 1), np.stack([x[::-1], lo[::-1]], 1)])
    pts = curves.resample(np.vstack([ring, ring[:1]]), n + 1)[:-1]
    return np.round(pts, 2)


def top_outline(S, xs, zs, n=24):
    inside = (S < 0).any(1)                            # (nx, nz)
    cols = np.nonzero(inside.any(1))[0]
    zt = np.array([zs[np.nonzero(inside[i])[0].max()] for i in cols])
    x = xs[cols]
    chain = np.vstack([[x[0], 0.0], np.stack([x, zt], 1), [x[-1], 0.0]])
    pts = curves.resample(chain, n)
    pts[0, 1] = pts[-1, 1] = 0.0
    return np.round(pts, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("out")
    ap.add_argument("stations", type=float, nargs="+")
    ap.add_argument("--views-strength", type=float, default=0.5)
    ap.add_argument("--no-views", action="store_true")
    ap.add_argument("--voxel", type=float, default=0.3)
    ap.add_argument("--tol", type=float, default=TOL)
    ap.add_argument("--name")
    a = ap.parse_args()
    S = np.load(f"{a.ref}/sdf_noscrews.npy")
    m = np.load(f"{a.ref}/meta.npz")
    xs, ys, zs = m["xs"], m["ys"], m["zs"]
    stations = []
    for x in a.stations:
        xg, P = section_contour(S, xs, ys, zs, x)
        ctrl, lm, err = fit_controls(P, a.tol)
        print(f"station x={xg:.2f}: {len(ctrl)} control points, fit error {err:.3f} mm", file=sys.stderr)
        stations.append({"x": round(xg, 3), "points": ctrl.tolist(), "landmarks": lm})
    spec = {
        "schema": "hold-spec/1",
        "name": a.name or "ravage_rebuild_%dst" % len(stations),
        "wall_angle_deg": 45,
        "description": "Ravage-inspired 25 mm incut crimp, rebuilt from sections extracted from v2.",
        "stations": stations,
        "mounting": {"screws": [[-40.0, 37.7], [42.0, 39.9]], "hole_dia": 4.8, "countersink_dia": 10.0},
        "build": {"voxel": a.voxel, "smooth_sigma_vox": 0.5},
    }
    if not a.no_views:
        spec["front_view"] = {"points": front_outline(S, xs, ys).tolist(), "strength": a.views_strength}
        spec["top_view"] = {"points": top_outline(S, xs, zs).tolist(), "strength": a.views_strength}
    with open(a.out, "w") as f:
        json.dump(spec, f, indent=1)


if __name__ == "__main__":
    main()
