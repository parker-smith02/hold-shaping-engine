"""Local sculpt features applied to the SDF as smooth displacements.

Positive depth removes material (pushes the surface in by about `depth` mm at the
centre); negative depth adds material.

  {"type": "dent",   "center": [x, y, z], "size": [sx, sy, sz], "depth": 1.5}
      Gaussian blob; size is the 1-sigma radius along each axis (mm).
  {"type": "groove", "path": [[x, y, z], ...], "width": 8, "depth": 0.7}
      Gaussian channel along a 3D polyline; width ~ full width at 1/e depth.

Anchors may instead be 2D with "surface": "front" ([x, y] in the front view) or
"surface": "ledge" ([x, z] in the top view); they are projected onto the hold.
"""
import numpy as np


def _box(axes, lo, hi):
    sl = []
    for a, a0, a1 in zip(axes, lo, hi):
        i0 = max(int(np.searchsorted(a, a0)) - 1, 0)
        i1 = min(int(np.searchsorted(a, a1)) + 1, len(a))
        sl.append(slice(i0, i1))
    return tuple(sl)


def project(S, axes, p, surface):
    """Lift a 2D anchor onto the hold surface.
    surface 'front': p = [x, y] (front view) -> outermost z of the hold there.
    surface 'ledge': p = [x, z] (top view)   -> highest y of the hold there (the ledge)."""
    xs, ys, zs = axes
    i = int(np.argmin(np.abs(xs - p[0])))
    if surface == "front":
        j = int(np.argmin(np.abs(ys - p[1])))
        k = np.nonzero(S[i, j] < 0)[0]
        return [p[0], p[1], float(zs[k.max()]) if len(k) else 0.0]
    if surface == "ledge":
        k = int(np.argmin(np.abs(zs - p[1])))
        j = np.nonzero(S[i, :, k] < 0)[0]
        return [p[0], float(ys[j.max()]) if len(j) else 0.0, p[1]]
    raise ValueError(f"unknown surface {surface!r} (use 'front' or 'ledge', or give [x, y, z])")


def resolve(S, axes, features):
    """Fill in 3D coordinates for features anchored in the front or top view."""
    out = []
    for f in features:
        f = dict(f)
        surf = f.get("surface")
        if f["type"] == "dent" and len(f["center"]) == 2:
            f["center"] = project(S, axes, f["center"], surf)
        if f["type"] == "groove" and len(f["path"][0]) == 2:
            f["path"] = [project(S, axes, p, surf) for p in f["path"]]
        out.append(f)
    return out


def apply(S, axes, features):
    xs, ys, zs = axes
    features = resolve(S, axes, features)
    for f in features:
        A = float(f["depth"])
        if f["type"] == "dent":
            c = np.asarray(f["center"], float)
            s = np.asarray(f["size"], float)
            sl = _box(axes, c - 3 * s, c + 3 * s)
            X, Y, Z = np.meshgrid(xs[sl[0]], ys[sl[1]], zs[sl[2]], indexing="ij")
            S[sl] += (A * np.exp(-(((X - c[0]) / s[0]) ** 2 + ((Y - c[1]) / s[1]) ** 2
                                   + ((Z - c[2]) / s[2]) ** 2))).astype(np.float32)
        elif f["type"] == "groove":
            P = np.asarray(f["path"], float)
            w = float(f["width"]) / 2
            sl = _box(axes, P.min(0) - 3 * w, P.max(0) + 3 * w)
            X, Y, Z = np.meshgrid(xs[sl[0]], ys[sl[1]], zs[sl[2]], indexing="ij")
            Q = np.stack([X, Y, Z], -1)
            dmin = np.full(X.shape, np.inf)
            for a, b in zip(P[:-1], P[1:]):
                ab = b - a
                t = np.clip(((Q - a) @ ab) / max(ab @ ab, 1e-9), 0, 1)
                dmin = np.minimum(dmin, np.linalg.norm(Q - (a + t[..., None] * ab), axis=-1))
            S[sl] += (A * np.exp(-(dmin / w) ** 2)).astype(np.float32)
    return S
