"""Fit spline control points to a dense section curve.

Used to start a new station from the current loft (`section_at`) and by the research
tools that extract stations from reference geometry.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from . import curves
from .loft import Loft


def fit_controls(poly: np.ndarray, tol: float = 0.12, must=(), max_points: int = 80):
    """Greedy: start from `must` (+ both ends), add the worst-fitting sample until the
    centripetal Catmull-Rom through the chosen samples is within `tol` mm everywhere.
    Returns (sorted sample indices, max error)."""
    n = len(poly)
    sel = sorted({0, n - 1, *[int(m) for m in must]})
    err = np.inf
    for _ in range(max_points):
        dense, _ = curves.eval_open(poly[sel], step=0.05)
        d, _ = cKDTree(dense).query(poly)
        j = int(np.argmax(d))
        err = float(d[j])
        if err < tol:
            break
        sel = sorted(set(sel) | {j})
    return sel, err


def section_at(spec: dict, x: float, tol: float = 0.12) -> dict:
    """A new station at x shaped like the current loft there, with the spec's landmarks."""
    L = Loft(spec)
    P, ok = L.at([x])
    if not ok[0]:
        raise ValueError(f"x = {x:g} is outside the hold ({L.x_min:g} to {L.x_max:g})")
    poly = P[0].copy()
    poly[0, 0] = poly[-1, 0] = 0.0
    names = [k for k in spec["landmark_order"] if k not in ("bottom_root", "ledge_root")]
    lm = {k: int(L.landmark_index[k]) for k in names}
    sel, _ = fit_controls(poly, tol, must=lm.values())
    return {"x": float(x), "points": [[round(float(a), 3), round(float(b), 3)] for a, b in poly[sel]],
            "landmarks": {k: sel.index(v) for k, v in lm.items()}, "corners": [], "note": ""}
