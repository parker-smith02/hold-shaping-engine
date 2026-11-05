"""Turn lofted sections into a 3D signed distance field (negative inside, mm).

Each x slice is a 2D SDF of its section. The section is treated as mirrored across
the wall (z -> -z), so distances near the wall are measured to the drawn curve only;
the flat back is applied later with max(d, -z). Distances are exact (to ~0.01 mm)
inside a narrow band and clipped to +/-BAND outside it.
"""
import numpy as np
from matplotlib.path import Path
from scipy.spatial import cKDTree

from . import curves

BAND = 6.0


def slice_sdf(poly, Zg, Yg):
    """poly (N,2) [z, y] open curve with both ends on the wall. Zg, Yg: grid arrays."""
    mir = np.vstack([poly, poly[::-1] * [-1, 1]])
    pts = np.stack([Zg.ravel(), Yg.ravel()], 1)
    inside = Path(mir, closed=True).contains_points(np.stack([np.abs(pts[:, 0]), pts[:, 1]], 1))
    dense = curves.densify(mir, 0.04)
    d, _ = cKDTree(dense).query(pts, distance_upper_bound=BAND)
    d = np.minimum(d, BAND)
    return np.where(inside, -d, d).reshape(Zg.shape).astype(np.float32)


_GRID = {}


def _worker(poly):
    return slice_sdf(poly, _GRID["Z"], _GRID["Y"])


def _map_slices(polys, Zg, Yg):
    """slice_sdf over many slices, spread across CPU cores when available."""
    import multiprocessing as mp
    import os
    n = min(os.cpu_count() or 1, 8)
    if n < 2 or len(polys) < 16 or "fork" not in mp.get_all_start_methods():
        return [slice_sdf(p, Zg, Yg) for p in polys]
    _GRID["Z"], _GRID["Y"] = Zg, Yg
    with mp.get_context("fork").Pool(n) as pool:
        return pool.map(_worker, polys, chunksize=max(1, len(polys) // (4 * n)))


def build(loft, vox):
    """Returns S (nx, ny, nz) and grid axes (xs, ys, zs)."""
    caps = {s: loft.tip[s]["radius"] if loft.tip[s]["kind"] == "cap" else 0.0 for s in ("left", "right")}
    x0 = loft.x_min - caps["left"] - 2.0
    x1 = loft.x_max + caps["right"] + 2.0
    xs = np.arange(x0, x1 + vox, vox)
    polys, valid = loft.at(xs)
    P = polys[valid]
    ys = np.arange(P[..., 1].min() - 3.0, P[..., 1].max() + 3.0, vox)
    zs = np.arange(-1.0 + vox * 0.5, P[..., 0].max() + 3.0, vox)
    Zg, Yg = np.meshgrid(zs, ys)                      # (ny, nz)
    S = np.full((len(xs), len(ys), len(zs)), BAND, np.float32)
    idx = np.nonzero(valid)[0]
    for i, sl in zip(idx, _map_slices([polys[i] for i in idx], Zg, Yg)):
        S[i] = sl
    # rounded end caps where no view carries the hold past the outermost station
    for side, sgn, k in (("left", -1, 0), ("right", 1, -1)):
        R = caps[side]
        if R <= 0:
            continue
        xe = loft.xs[k]
        end = slice_sdf(loft.M[k], Zg, Yg)
        for i in range(len(xs)):
            dx = (xs[i] - xe) * sgn
            if dx > 0:
                S[i] = np.minimum(end + (R - np.sqrt(max(R * R - dx * dx, 0.0))) if dx < R else BAND, BAND)
    return S, (xs, ys, zs)


def normalize_gradient(S, vox):
    """Stacked slice distances overestimate true 3D distance where the surface leans
    along x (tips). Divide by the gradient magnitude to get a first-order correction."""
    g = np.zeros_like(S)
    for ax in range(3):
        gi = np.gradient(S, vox, axis=ax)
        g += gi * gi
    g = np.sqrt(g)
    band = np.abs(S) < BAND - 1
    S[band] = S[band] / np.clip(g[band], 1.0, 4.0)
    return S
