"""Assemble the full hold SDF from a spec: loft -> SDF -> features -> back -> screws."""
import time
import numpy as np
from scipy import ndimage

from . import loft as loft_mod, sdf, features


def screws(S, axes, mounting):
    xs, ys, zs = axes
    r_hole = mounting["hole_dia"] / 2
    r_cs = mounting["countersink_dia"] / 2
    info = []
    Z = zs[None, None, :]
    for sx, sy in mounting["screws"]:
        i = int(np.argmin(np.abs(xs - sx)))
        j = int(np.argmin(np.abs(ys - sy)))
        col = np.nonzero(S[i, j] < 0)[0]
        if len(col) == 0:
            info.append({"x": sx, "y": sy, "face_thickness": 0.0, "warning": "screw is outside the hold"})
            continue
        face = float(zs[col.max()])
        reach = int((r_cs + (zs[-1] - face) + 2) / (xs[1] - xs[0]))   # cone keeps widening on a sloped face
        sl_x = slice(max(i - reach, 0), i + reach + 1)
        sl_y = slice(max(j - reach, 0), j + reach + 1)
        X, Y = np.meshgrid(xs[sl_x], ys[sl_y], indexing="ij")
        rs = np.sqrt((X - sx) ** 2 + (Y - sy) ** 2)[:, :, None]
        r = r_hole + np.maximum(Z - (face - (r_cs - r_hole)), 0)    # 90 deg countersink
        S[sl_x, sl_y] = np.maximum(S[sl_x, sl_y], -(rs - r)).astype(np.float32)
        info.append({"x": sx, "y": sy, "face_thickness": round(face, 1)})
    return S, info


def build(spec, log=print):
    t0 = time.time()
    vox = float(spec["build"]["voxel"])
    L = loft_mod.Loft(spec)
    S, axes = sdf.build(L, vox)
    log(f"  sections lofted and sliced: grid {S.shape}, {time.time() - t0:.1f}s")
    S = sdf.normalize_gradient(S, vox)
    S = features.apply(S, axes, spec["features"])
    S = np.maximum(S, -axes[2][None, None, :]).astype(np.float32)         # flat back
    S, screw_info = screws(S, axes, spec["mounting"])
    sig = float(spec["build"]["smooth_sigma_vox"])
    if sig > 0:
        S = ndimage.gaussian_filter(S, sig)
    S[0], S[-1] = sdf.BAND, sdf.BAND
    S[:, 0], S[:, -1] = sdf.BAND, sdf.BAND
    S[:, :, 0], S[:, :, -1] = sdf.BAND, sdf.BAND
    log(f"  SDF done in {time.time() - t0:.1f}s")
    return S, axes, L, screw_info
