"""Compare a rebuilt hold against the original Ravage v2 SDF (screw-free).

    python3 compare.py REF_DIR rebuilt.stl spec.json out.png
Prints surface deviation stats and writes a deviation map (front view + |dev| along x).
"""
import json
import sys

import numpy as np
from scipy.ndimage import map_coordinates
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", ".."))
from holdgen import mesh  # noqa: E402


def sample(S, axes, P):
    xs, ys, zs = axes
    vox = xs[1] - xs[0]
    idx = [(P[:, 0] - xs[0]) / vox, (P[:, 1] - ys[0]) / vox, (P[:, 2] - zs[0]) / vox]
    return map_coordinates(S, idx, order=1, mode="nearest")


def main(ref, stl, spec_path, out_png):
    spec = json.load(open(spec_path))
    S = np.load(f"{ref}/sdf_noscrews.npy")
    m = np.load(f"{ref}/meta.npz")
    axes = (m["xs"], m["ys"], m["zs"])
    V, T = mesh.read_stl(stl)
    keep = V[:, 2] > 0.05                                   # skip the flat back
    for sx, sy in spec["mounting"]["screws"]:
        keep &= np.hypot(V[:, 0] - sx, V[:, 1] - sy) > spec["mounting"]["countersink_dia"] / 2 + 6
    P = V[keep]
    d = sample(S, axes, P)                                  # + = rebuilt surface is outside the original
    a = np.abs(d)
    print(f"surface deviation from original v2 (screw areas excluded): mean {a.mean():.3f}  "
          f"p50 {np.median(a):.3f}  p95 {np.percentile(a, 95):.3f}  max {a.max():.3f} mm")
    bins = np.arange(np.floor(P[:, 0].min()), P[:, 0].max() + 2, 2.0)
    k = np.digitize(P[:, 0], bins)
    bx = np.array([bins[i - 1] + 1 for i in np.unique(k)])
    bmax = np.array([a[k == i].max() for i in np.unique(k)])
    bp95 = np.array([np.percentile(a[k == i], 95) for i in np.unique(k)])
    sx = [s["x"] for s in spec["stations"]]
    core = (P[:, 0] > min(sx)) & (P[:, 0] < max(sx))
    print(f"  between outer stations: mean {a[core].mean():.3f}  p95 {np.percentile(a[core], 95):.3f}  "
          f"max {a[core].max():.3f} mm;  tips: mean {a[~core].mean():.3f}  max {a[~core].max():.3f} mm")
    fig, ax = plt.subplots(2, 1, figsize=(13, 8.5), gridspec_kw={"height_ratios": [1.3, 1]})
    o = np.argsort(P[:, 2])
    sc = ax[0].scatter(P[o, 0], P[o, 1], c=d[o], s=1.2, cmap="RdBu_r", vmin=-1, vmax=1)
    for x in sx:
        ax[0].axvline(x, color="k", lw=0.6, ls=":")
    ax[0].set_aspect("equal")
    ax[0].set_title("front view, signed deviation from original v2 (red = rebuilt sticks out, blue = rebuilt "
                    "is inside); dotted = stations", fontsize=9)
    plt.colorbar(sc, ax=ax[0], label="mm", shrink=0.8)
    ax[1].plot(bx, bmax, label="max |dev|")
    ax[1].plot(bx, bp95, label="p95 |dev|")
    for x in sx:
        ax[1].axvline(x, color="k", lw=0.6, ls=":")
    ax[1].set_xlabel("x (mm)"); ax[1].set_ylabel("mm"); ax[1].grid(alpha=0.3); ax[1].legend()
    ax[1].set_title(f"{spec['name']}: deviation along the hold", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_png, dpi=100)


if __name__ == "__main__":
    main(*sys.argv[1:5])
