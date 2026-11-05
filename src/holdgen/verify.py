"""Check a built mesh against the drawn sections and report hold readouts.

Readouts (depth, incut, ledge angle on the wall, thickness) are information only:
the spec has no target values, the drawn splines are the authority.
"""
import numpy as np
from scipy.spatial import cKDTree

from . import curves


def slice_mesh(V, T, x0):
    """Intersect the mesh with the plane x = x0. Returns segments (n, 2, 2) as [z, y]."""
    s = V[:, 0] - (x0 + 1e-7)
    sa, sb, sc = s[T[:, 0]], s[T[:, 1]], s[T[:, 2]]
    hit = ~(((sa > 0) & (sb > 0) & (sc > 0)) | ((sa < 0) & (sb < 0) & (sc < 0)))
    Th = T[hit]
    pts = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        va, vb = V[Th[:, a]], V[Th[:, b]]
        fa, fb = s[Th[:, a]], s[Th[:, b]]
        cross = (fa > 0) != (fb > 0)
        t = np.where(cross, fa / np.where(cross, fa - fb, 1), np.nan)
        p = va + t[:, None] * (vb - va)
        pts.append(np.where(cross[:, None], p[:, [2, 1]], np.nan))
    P = np.stack(pts, 1)                               # (n, 3, 2), exactly two valid per tri
    ok = ~np.isnan(P[..., 0])
    keep = ok.sum(1) == 2
    P, ok = P[keep], ok[keep]
    return P[ok].reshape(-1, 2, 2)


def _seg_points(seg, k=4):
    t = np.linspace(0, 1, k + 1)[:, None, None]
    return (seg[None, :, 0] * (1 - t) + seg[None, :, 1] * t).reshape(-1, 2)


def deviation(drawn, seg):
    """Two-way distance between a drawn curve and a built mesh slice (mm)."""
    built = _seg_points(seg)
    built_wo_back = built[built[:, 0] > 0.05]
    d1, _ = cKDTree(built).query(curves.densify(drawn, 0.05))
    d2, _ = cKDTree(curves.densify(drawn, 0.02)).query(built_wo_back)
    return {"max": float(max(d1.max(), d2.max())), "mean": float(np.concatenate([d1, d2]).mean()),
            "p95": float(np.percentile(np.concatenate([d1, d2]), 95))}


def readouts(poly, apex_index=None, wall_angle=45.0):
    """Hold anatomy numbers from an ordered section polyline [z, y] (bottom root -> ledge root)."""
    z, y = poly[:, 0], poly[:, 1]
    y0 = y[-1]
    j = int(np.argmax(y)) if apex_index is None else int(apex_index)
    u = np.array([z[j], y[j] - y0])
    u /= np.linalg.norm(u)
    top = y > y0 - 6
    depth = float((z[top] * u[0] + (y[top] - y0) * u[1]).max())
    chord = float(np.degrees(np.arctan2(u[1], u[0])))
    led = poly[j:]                                   # lip apex -> ledge root
    lz, ly = led[::-1, 0], led[::-1, 1]              # root outward

    def ang(z0, z1):
        k = (lz >= z0) & (lz <= z1)
        if k.sum() < 2:
            return None
        lz_k, ly_k = lz[k], ly[k]
        return round(float(np.degrees(np.arctan(np.polyfit(lz_k, ly_k, 1)[0]))), 1)

    return {"depth": round(depth, 1), "chord_incut": round(chord, 1),
            "incut_at_wall": ang(0.5, 5.0), "incut_near_lip": ang(z[j] - 7, z[j] - 2),
            "ledge_below_horizontal_on_wall": round(wall_angle - chord, 1),
            "thickness": round(float(z.max()), 1), "height": round(float(np.ptp(y)), 1)}


def print_overhangs(V, T, limit=50.0):
    """Downward-facing area steeper than `limit` deg from vertical when printed back-down."""
    v0, v1, v2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    n = np.cross(v1 - v0, v2 - v0)
    a = np.linalg.norm(n, axis=1)
    n = n / np.maximum(a, 1e-12)[:, None]
    back = (v0[:, 2] < 0.05) & (v1[:, 2] < 0.05) & (v2[:, 2] < 0.05)
    ang = np.degrees(np.arcsin(np.clip(-n[:, 2], -1, 1)))
    m = (ang > limit) & ~back
    area = float(a[m].sum() / 2)
    out = {"limit_deg": limit, "area_mm2": round(area, 0)}
    if area > 0:
        c = (v0[m] + v1[m] + v2[m]) / 3
        out["x_range"] = [round(float(c[:, 0].min()), 1), round(float(c[:, 0].max()), 1)]
        out["max_deg"] = round(float(ang[m].max()), 1)
    return out


def run(spec, L, V, T):
    wall = float(spec["wall_angle_deg"])
    apex_i = L.landmark_index.get("lip_apex")
    stations = []
    for i, st in enumerate(spec["stations"]):
        seg = slice_mesh(V, T, st["x"])
        dev = deviation(L.dense[i], seg)
        apex_dense = None
        if "lip_apex" in st["landmarks"]:
            ci = curves.eval_open(st["points"], st.get("corners", []))[1]
            apex_dense = ci[st["landmarks"]["lip_apex"]]
        near_screw = any(abs(st["x"] - sx) < spec["mounting"]["countersink_dia"] / 2 + 1
                         for sx, _ in spec["mounting"]["screws"])
        stations.append({"x": st["x"], "deviation_mm": {k: round(v, 3) for k, v in dev.items()},
                         "cuts_screw": near_screw,
                         "readouts": readouts(L.dense[i], apex_dense, wall), "segments": seg})
    # between stations: readouts on the lofted (pre-mesh) section
    mids = []
    xs = L.xs
    for a, b in zip(xs[:-1], xs[1:]):
        xm = 0.5 * (a + b)
        P, ok = L.at([xm])
        if ok[0]:
            mids.append({"x": float(xm), "readouts": readouts(P[0], apex_i, wall),
                         "segments": slice_mesh(V, T, xm), "lofted": P[0]})
    return {"stations": stations, "between": mids, "overhangs": print_overhangs(V, T)}
