"""Spline evaluation and landmark-based resampling.

All drawn curves are centripetal Catmull-Rom splines that pass *through* their
control points. A control point flagged as a corner splits the spline there, so
the curve keeps its position but loses tangent continuity at that point.
"""
import numpy as np

DENSE_STEP = 0.02  # mm between samples when densifying a spline


def _cr_segment(p0, p1, p2, p3, n, alpha=0.5):
    """Barry-Goldman evaluation of one centripetal Catmull-Rom span p1->p2.
    Returns n points, including p1 and excluding p2."""
    def tj(ti, a, b):
        d = np.linalg.norm(b - a)
        return ti + max(d, 1e-9) ** alpha
    t0 = 0.0
    t1 = tj(t0, p0, p1)
    t2 = tj(t1, p1, p2)
    t3 = tj(t2, p2, p3)
    t = np.linspace(t1, t2, n, endpoint=False)[:, None]
    a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
    a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
    a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
    b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
    b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
    return (t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2


def _open_piece(P, step):
    """Dense samples of an open spline through all of P (no corners inside).
    Returns (dense points, index into dense of each control point)."""
    n = len(P)
    if n == 1:
        return P.copy(), np.array([0])
    ext = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out, idx = [], []
    count = 0
    for i in range(n - 1):
        m = max(4, int(np.ceil(np.linalg.norm(P[i + 1] - P[i]) / step)))
        seg = _cr_segment(ext[i], ext[i + 1], ext[i + 2], ext[i + 3], m)
        idx.append(count)
        out.append(seg)
        count += len(seg)
    out.append(P[-1:])
    idx.append(count)
    return np.vstack(out), np.array(idx)


def eval_open(points, corners=(), step=DENSE_STEP):
    """Dense polyline through `points` (open curve), honoring corner indices.
    Returns (dense (M,2), ctrl_idx (n,)) where dense[ctrl_idx[i]] == points[i]."""
    P = np.asarray(points, float)
    cuts = sorted(set(int(c) for c in corners if 0 < int(c) < len(P) - 1))
    bounds = [0] + cuts + [len(P) - 1]
    dense, idx = [], []
    offset = 0
    for a, b in zip(bounds[:-1], bounds[1:]):
        d, ii = _open_piece(P[a:b + 1], step)
        if dense:                       # drop the shared corner point
            d, ii = d[1:], ii[1:] - 1
        dense.append(d)
        idx.extend((ii + offset).tolist())
        offset += len(d)
    return np.vstack(dense), np.array(idx)


def eval_closed(points, corners=(), step=DENSE_STEP):
    """Dense closed polyline through `points` (last point joins the first)."""
    P = np.asarray(points, float)
    n = len(P)
    if n < 3:
        raise ValueError("a closed outline needs at least 3 points")
    cs = set(int(c) % n for c in corners)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = P[(i - 1) % n], P[i], P[(i + 1) % n], P[(i + 2) % n]
        if i in cs:
            p0 = 2 * p1 - p2
        if (i + 1) % n in cs:
            p3 = 2 * p2 - p1
        m = max(4, int(np.ceil(np.linalg.norm(p2 - p1) / step)))
        out.append(_cr_segment(p0, p1, p2, p3, m))
    return np.vstack(out)


def arclen(poly):
    d = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(d)])


def resample(poly, n):
    """n points evenly spaced by arc length along poly (both ends included)."""
    s = arclen(poly)
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, poly[:, 0]), np.interp(t, s, poly[:, 1])], 1)


def densify(poly, step):
    """Linear upsampling so consecutive points are at most `step` apart."""
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    k = np.maximum(1, np.ceil(seg / step).astype(int))
    pts = [poly[i] + (poly[i + 1] - poly[i]) * (np.arange(k[i])[:, None] / k[i])
           for i in range(len(poly) - 1)]
    pts.append(poly[-1:])
    return np.vstack(pts)
