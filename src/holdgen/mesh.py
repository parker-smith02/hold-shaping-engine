"""SDF -> watertight triangle mesh -> binary STL, plus mesh checks."""
import numpy as np


def from_sdf(S, axes, step=1):
    from skimage.measure import marching_cubes
    xs, ys, zs = axes
    vox = float(xs[1] - xs[0])
    V, T, _, _ = marching_cubes(S, 0.0, spacing=(vox, vox, vox), step_size=step, allow_degenerate=False)
    V = V.astype(np.float64) + [xs[0], ys[0], zs[0]]
    V[np.abs(V[:, 2]) < 0.02, 2] = 0.0             # snap the back exactly flat
    T = T.astype(np.int64)
    if volume(V, T) < 0:
        T = T[:, ::-1].copy()
    return V, T


def volume(V, T):
    v0, v1, v2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6)


def check(V, T):
    n = len(V)
    E = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    k = np.sort(E, 1)
    _, c = np.unique(k[:, 0] * n + k[:, 1], return_counts=True)
    _, dc = np.unique(E[:, 0] * n + E[:, 1], return_counts=True)
    return {
        "vertices": int(n), "triangles": int(len(T)),
        "edges_not_shared_by_two": int((c != 2).sum()),
        "directed_duplicate_edges": int((dc > 1).sum()),
        "watertight": bool((c == 2).all() and (dc == 1).all()),
        "volume_cm3": round(volume(V, T) / 1000, 2),
        "bbox_min": V.min(0).round(2).tolist(), "bbox_max": V.max(0).round(2).tolist(),
        "size_mm": (V.max(0) - V.min(0)).round(1).tolist(),
    }


def write_stl(path, V, T, header="holdgen blank, units mm"):
    v0, v1, v2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    nrm = np.cross(v1 - v0, v2 - v0)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    rec = np.zeros(len(T), dtype=[("n", "<f4", 3), ("v", "<f4", 9), ("a", "<u2")])
    rec["n"] = nrm
    rec["v"] = np.hstack([v0, v1, v2])
    with open(path, "wb") as f:
        f.write(header.encode()[:80].ljust(80, b" "))
        f.write(np.uint32(len(T)).tobytes())
        f.write(rec.tobytes())


def read_stl(path):
    with open(path, "rb") as f:
        f.read(80)
        n = int(np.frombuffer(f.read(4), np.uint32)[0])
        rec = np.frombuffer(f.read(n * 50), dtype=[("n", "<f4", 3), ("v", "<f4", 9), ("a", "<u2")])
    P = rec["v"].reshape(-1, 3).astype(np.float64)
    U, inv = np.unique(P.round(5), axis=0, return_inverse=True)
    return U, inv.reshape(-1, 3)
