"""Interactive preview geometry, computed by the same loft as the full build.

The editor never reimplements lofting: it sends the spec here and receives
  * a skinned triangle mesh of the lofted sections (with features displaced along
    vertex normals, the same displacement the SDF build applies),
  * per-x extents for the front/top panes,
  * readouts at every station and midway between stations,
  * screw face positions.

Differences from the full build (all small and stated): no SDF smoothing, rounded
caps are approximated by insetting the end section along its normals, and screw
holes are not cut (they are returned as positions).
"""
from __future__ import annotations

import base64
import math

import numpy as np

from . import curves, verify
from .loft import Loft


def _b64(a: np.ndarray, dtype) -> str:
    return base64.b64encode(np.ascontiguousarray(a, dtype=dtype).tobytes()).decode("ascii")


def rings(L: Loft, dx: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Section rings along x. Returns (xs (R,), rows (R, N, 2) as [z, y])."""
    xs = set(np.arange(math.ceil(L.x_min), math.floor(L.x_max) + 1e-9, dx).round(6).tolist())
    xs |= set(L.xs.tolist()) | {L.x_min + 0.05, L.x_max - 0.05}
    xq = np.array(sorted(x for x in xs if L.x_min <= x <= L.x_max))
    P, ok = L.at(xq)
    xr, rows = list(xq[ok]), list(P[ok])
    for side, sgn, k in (("left", -1, 0), ("right", 1, -1)):
        tip = L.tip[side]
        if tip["kind"] != "cap":
            continue
        E, R = L.M[k], tip["radius"]
        t = np.gradient(E, axis=0)
        t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
        inward = np.stack([-t[:, 1], t[:, 0]], 1)            # left normal of a CCW traversal in (z, y)
        add_x, add_r = [], []
        for j in range(1, 7):
            d = R * j / 6.2
            inset = R - math.sqrt(R * R - d * d)
            row = E + inward * inset
            row[:, 0] = np.maximum(row[:, 0], 0)
            add_x.append(tip["x_end"] + sgn * d)
            add_r.append(row)
        if side == "left":
            xr, rows = add_x[::-1] + xr, add_r[::-1] + rows
        else:
            xr, rows = xr + add_x, rows + add_r
    return np.array(xr), np.stack(rows)


def skin(xr: np.ndarray, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Closed, outward-facing triangle mesh from rings. Each ring is closed along the wall
    (ledge root -> bottom root) and the two end rings are capped with fans."""
    R, N, _ = rows.shape
    V = np.zeros((R * N + 2, 3))
    V[:R * N, 0] = np.repeat(xr, N)
    V[:R * N, 1] = rows[..., 1].ravel()
    V[:R * N, 2] = rows[..., 0].ravel()
    for slot, r in ((R * N, 0), (R * N + 1, R - 1)):
        V[slot] = [xr[r], rows[r, :, 1].mean(), rows[r, :, 0].mean() * 0.5]
    i = np.arange(R - 1)[:, None]
    k = np.arange(N)[None, :]
    k2 = (k + 1) % N
    a, b, c, d = i * N + k, i * N + k2, (i + 1) * N + k2, (i + 1) * N + k
    quads = np.stack([np.stack([a, b, c], -1), np.stack([a, c, d], -1)], -2).reshape(-1, 3)
    kk = np.arange(N)
    fan0 = np.stack([np.full(N, R * N), (kk + 1) % N, kk], 1)
    fan1 = np.stack([np.full(N, R * N + 1), (R - 1) * N + kk, (R - 1) * N + (kk + 1) % N], 1)
    T = np.vstack([quads, fan0, fan1]).astype(np.int64)
    v0, v1, v2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    if np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() < 0:
        T = T[:, ::-1].copy()
    return V, T


def vertex_normals(V: np.ndarray, T: np.ndarray) -> np.ndarray:
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])     # area weighted
    out = np.zeros_like(V)
    for j in range(3):
        np.add.at(out, T[:, j], n)
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)


def _anchor(V: np.ndarray, p, surface):
    if len(p) == 3:
        return np.asarray(p, float)
    if surface == "front":
        m = (np.abs(V[:, 0] - p[0]) < 1.2) & (np.abs(V[:, 1] - p[1]) < 1.2)
        return V[m][np.argmax(V[m, 2])] if m.any() else None
    m = (np.abs(V[:, 0] - p[0]) < 1.2) & (np.abs(V[:, 2] - p[1]) < 1.2)
    return V[m][np.argmax(V[m, 1])] if m.any() else None


def displace_features(V: np.ndarray, T: np.ndarray, features: list) -> np.ndarray:
    if not features:
        return V
    nrm = vertex_normals(V, T)
    disp = np.zeros(len(V))
    for f in features:
        if f["type"] == "dent":
            c = _anchor(V, f["center"], f.get("surface"))
            if c is None:
                continue
            s = np.asarray(f["size"], float)
            q = (((V - c) / s) ** 2).sum(1)
            disp += np.where(q < 9, f["depth"] * np.exp(-q), 0)
        else:
            P = [a for a in (_anchor(V, p, f.get("surface")) for p in f["path"]) if a is not None]
            if len(P) < 2:
                continue
            w = f["width"] / 2
            dmin = np.full(len(V), np.inf)
            for a, b in zip(P[:-1], P[1:]):
                ab = b - a
                t = np.clip(((V - a) @ ab) / max(ab @ ab, 1e-9), 0, 1)
                dmin = np.minimum(dmin, np.linalg.norm(V - (a + t[:, None] * ab), axis=1))
            disp += np.where(dmin < 3 * w, f["depth"] * np.exp(-(dmin / w) ** 2), 0)
    disp[V[:, 2] < 0.05] = 0                                            # the back stays flat
    return V - nrm * disp[:, None]


def _screw_faces(L: Loft, screws):
    out = []
    if not screws:
        return out
    P, ok = L.at([s[0] for s in screws])
    for (sx, sy), row, good in zip(screws, P, ok):
        fz = 0.0
        if good:
            y0, y1 = row[:-1, 1], row[1:, 1]
            cross = (y0 - sy) * (y1 - sy) <= 0
            if cross.any():
                fz = float(((row[:-1, 0] + row[1:, 0]) / 2)[cross].max())
        out.append({"x": sx, "y": sy, "face_z": round(fz, 2)})
    return out


def preview(spec: dict, step: float = 0.4, dx: float = 1.0) -> dict:
    """Preview payload for the editor. `spec` is an engine dict (spec.normalize)."""
    s = {**spec, "build": {**spec["build"], "sample_step": step}}
    L = Loft(s)
    xr, rows = rings(L, dx)
    V, T = skin(xr, rows)
    V = displace_features(V, T, spec["features"])
    wall = float(spec["wall_angle_deg"])
    apex = L.landmark_index.get("lip_apex")
    table = []
    for i, st in enumerate(spec["stations"]):
        a = None
        if "lip_apex" in st["landmarks"]:
            a = curves.eval_open(st["points"], st.get("corners", []))[1][st["landmarks"]["lip_apex"]]
        table.append({"x": st["x"], "kind": "station", "readouts": verify.readouts(L.dense[i], a, wall)})
    mids = 0.5 * (L.xs[:-1] + L.xs[1:])
    P, ok = L.at(mids)
    for xm, row, good in zip(mids, P, ok):
        if good:
            table.append({"x": float(xm), "kind": "between", "readouts": verify.readouts(row, apex, wall)})
    table.sort(key=lambda r: r["x"])
    bb0, bb1 = V.min(0), V.max(0)
    return {
        "loft": {"x_min": float(L.x_min), "x_max": float(L.x_max), "landmarks": list(spec["landmark_order"]),
                 "tips": {k: v["kind"] for k, v in L.tip.items()}},
        "extents": {"x": xr.round(3).tolist(), "y_lo": rows[..., 1].min(1).round(3).tolist(),
                    "y_hi": rows[..., 1].max(1).round(3).tolist(), "z_hi": rows[..., 0].max(1).round(3).tolist()},
        "mesh": {"positions": _b64(V, "<f4"), "indices": _b64(T, "<u4"),
                 "vertex_count": int(len(V)), "triangle_count": int(len(T))},
        "bbox": {"min": bb0.round(2).tolist(), "max": bb1.round(2).tolist()},
        "readouts": table,
        "screws": _screw_faces(L, spec["mounting"]["screws"]),
    }
