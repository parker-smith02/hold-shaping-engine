"""Preview renders (PIL painter's algorithm), section overlays and the spec sheet."""
import numpy as np
from PIL import Image, ImageDraw
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

COLOR = np.array([40, 95, 205], float)
BG = (246, 246, 244)


def _rot(yaw, pitch):
    cy, sy = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
    cp, sp = np.cos(np.radians(pitch)), np.sin(np.radians(pitch))
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    return Rx @ Rz


SIDE = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float)
VIEWS = [
    ("front (as on the wall)", _rot(0, 0), None, False),
    ("3/4 from above, onto the ledge", _rot(-25, -55), None, False),
    ("end view: wall on left, ledge at top", np.eye(3), SIDE, False),
    ("top-down onto the edge (wall at bottom)", _rot(0, 90), None, False),
    ("looking into the incut (wall removed)", _rot(-18, 118), None, True),
    ("3/4 from below-left", _rot(30, -35), None, False),
]


def view(V, T, R, W=820, H=560, pre=None, cull_back=False, title=None):
    P = V - V.mean(0)
    if pre is not None:
        P = P @ pre.T
    P = P @ R.T
    v0, v1, v2 = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    n = np.cross(v1 - v0, v2 - v0)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    vis = n[:, 2] > 0
    if cull_back:
        vis &= ~((V[T[:, 0], 2] < 0.05) & (V[T[:, 1], 2] < 0.05) & (V[T[:, 2], 2] < 0.05))
    L1 = np.array([-0.4, 0.6, 0.7]); L1 /= np.linalg.norm(L1)
    L2 = np.array([0.6, -0.2, 0.5]); L2 /= np.linalg.norm(L2)
    sh = 0.25 + 0.65 * np.clip(n @ L1, 0, 1) + 0.2 * np.clip(n @ L2, 0, 1)
    hv = (L1 + [0, 0, 1]) / np.linalg.norm(L1 + [0, 0, 1])
    spec = np.clip(n @ hv, 0, 1) ** 30 * 0.25
    col = np.clip(COLOR[None] * sh[:, None] + 255 * spec[:, None], 0, 255).astype(np.uint8)
    ss = 2
    scale = 0.86 * min(W / np.ptp(P[:, 0]), (H - 40) / np.ptp(P[:, 1])) * ss
    c = 0.5 * (P[:, :2].min(0) + P[:, :2].max(0))

    def px(p):
        return np.stack([(p[:, 0] - c[0]) * scale + W * ss / 2, -(p[:, 1] - c[1]) * scale + (H + 30) * ss / 2], 1)
    a, b, cc = px(v0), px(v1), px(v2)
    depth = v0[:, 2] + v1[:, 2] + v2[:, 2]
    idx = np.nonzero(vis)[0]
    idx = idx[np.argsort(depth[idx])]
    img = Image.new("RGB", (W * ss, H * ss), BG)
    d = ImageDraw.Draw(img)
    for i in idx:
        cl = tuple(col[i])
        d.polygon([tuple(a[i]), tuple(b[i]), tuple(cc[i])], fill=cl, outline=cl)
    img = img.resize((W, H), Image.LANCZOS)
    if title:
        ImageDraw.Draw(img).text((14, 12), title, fill=(70, 70, 70))
    return img


def preview_sheet(V, T, path, title=""):
    imgs = [view(V, T, R, pre=pre, cull_back=cb, title=t) for t, R, pre, cb in VIEWS]
    W, H = imgs[0].size
    sheet = Image.new("RGB", (W * 3, H * 2 + 40), BG)
    for k, im in enumerate(imgs):
        sheet.paste(im, ((k % 3) * W, 40 + (k // 3) * H))
    ImageDraw.Draw(sheet).text((14, 12), title, fill=(30, 30, 30))
    sheet.save(path)


def overlay(spec, L, report, path):
    st = report["stations"]
    mids = report["between"]
    n = max(len(st), len(mids))
    fig, axs = plt.subplots(2, n, figsize=(3.1 * n, 9.2), squeeze=False)
    allp = np.vstack([np.vstack(L.dense)] + [s["segments"].reshape(-1, 2) for s in st])
    zl = (-1.5, allp[:, 0].max() + 3)
    yl = (allp[:, 1].min() - 3, allp[:, 1].max() + 3)
    for k in range(n):
        for row in (0, 1):
            ax = axs[row, k]
            ax.set_xlim(*zl); ax.set_ylim(*yl); ax.set_aspect("equal")
            ax.axvline(0, color="k", lw=3)
            ax.tick_params(labelsize=7)
            ax.grid(alpha=0.25)
        if k < len(st):
            s, i = st[k], k
            ax = axs[0, k]
            ax.add_collection(LineCollection(s["segments"], colors="#2f62d0", linewidths=3.2, alpha=0.75))
            ax.plot(L.dense[i][:, 0], L.dense[i][:, 1], color="k", lw=0.8)
            pts = np.asarray(spec["stations"][i]["points"])
            ax.plot(pts[:, 0], pts[:, 1], "o", ms=2.5, color="#d04a2f")
            for name, ci in spec["stations"][i]["landmarks"].items():
                ax.annotate(name, pts[ci], fontsize=6, color="#d04a2f", xytext=(3, 3), textcoords="offset points")
            dv = s["deviation_mm"]
            flag = " (cuts screw)" if s["cuts_screw"] else ""
            ax.set_title(f"station x = {s['x']:g}{flag}\nmax {dv['max']:.2f}  mean {dv['mean']:.2f} mm",
                         fontsize=8)
        else:
            axs[0, k].axis("off")
        if k < len(mids):
            m = mids[k]
            ax = axs[1, k]
            if len(m["segments"]):
                ax.add_collection(LineCollection(m["segments"], colors="#2f62d0", linewidths=3.2, alpha=0.75))
            ax.plot(m["lofted"][:, 0], m["lofted"][:, 1], "--", color="k", lw=0.7)
            r = m["readouts"]
            ax.set_title(f"between, x = {m['x']:g}\ndepth {r['depth']}  chord incut {r['chord_incut']}°",
                         fontsize=8)
        else:
            axs[1, k].axis("off")
    axs[0, 0].set_ylabel("up the wall (mm)  -  STATIONS: black = drawn, blue = built", fontsize=8)
    axs[1, 0].set_ylabel("BETWEEN stations: dashed = lofted, blue = built", fontsize=8)
    fig.suptitle(f"{spec['name']}: drawn vs built sections (wall on left)", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def spec_sheet(spec, L, path):
    """What the spec says, drawn: front view, top view and every station."""
    ns = len(spec["stations"])
    fig = plt.figure(figsize=(max(12, 2.6 * ns), 10))
    gs = fig.add_gridspec(3, ns, height_ratios=[1.1, 0.7, 1.4])
    ax = fig.add_subplot(gs[0, :])
    xq = np.linspace(L.x_min, L.x_max, 500)
    P, ok = L.at(xq)
    ax.fill_between(xq[ok], P[ok][..., 1].min(1), P[ok][..., 1].max(1), color="#2f62d0", alpha=0.15,
                    label="lofted extent")
    if L.front is not None:
        f = np.vstack([L.front, L.front[:1]])
        ax.plot(f[:, 0], f[:, 1], "--", color="#555", lw=1.2,
                label=f"front view guide (strength {spec['front_view']['strength']})")
    for i, s in enumerate(spec["stations"]):
        d = L.dense[i]
        ax.plot([s["x"]] * 2, [d[:, 1].min(), d[:, 1].max()], color="#d04a2f", lw=2.5)
        ax.text(s["x"], d[:, 1].max() + 1.5, f"{s['x']:g}", ha="center", fontsize=7, color="#d04a2f")
    for sx, sy in spec["mounting"]["screws"]:
        ax.plot(sx, sy, "o", mfc="none", mec="k", ms=9)
    ledge_feats = []
    for ft in spec["features"]:
        c = np.atleast_2d(np.asarray(ft["center"] if ft["type"] == "dent" else ft["path"], float))
        if ft.get("surface") == "ledge":
            ledge_feats.append(c)                      # [x, z]: drawn on the top view
        else:
            ax.plot(c[:, 0], c[:, 1], "-x", color="#2a8a4a", lw=1)
    ax.set_aspect("equal"); ax.grid(alpha=0.25); ax.legend(fontsize=7, loc="upper right")
    ax.set_title("FRONT (on the wall): red = stations, circles = screws, green = features", fontsize=9)
    ax2 = fig.add_subplot(gs[1, :], sharex=ax)
    ax2.fill_between(xq[ok], 0, P[ok][..., 0].max(1), color="#2f62d0", alpha=0.15)
    if L.top is not None:
        t = L.top
        ax2.plot(t[:, 0], t[:, 1], "--", color="#555", lw=1.2)
    for i, s in enumerate(spec["stations"]):
        ax2.plot([s["x"]] * 2, [0, L.dense[i][:, 0].max()], color="#d04a2f", lw=2.5)
    for c in ledge_feats:
        ax2.plot(c[:, 0], c[:, 1], "-x", color="#2a8a4a", lw=1)
    ax2.axhline(0, color="k", lw=2)
    ax2.set_aspect("equal"); ax2.grid(alpha=0.25)
    ax2.set_title("TOP (looking down, wall at bottom): dashed = top view guide", fontsize=9)
    zmax = max(d[:, 0].max() for d in L.dense) + 3
    ylo = min(d[:, 1].min() for d in L.dense) - 3
    yhi = max(d[:, 1].max() for d in L.dense) + 3
    for i, s in enumerate(spec["stations"]):
        a = fig.add_subplot(gs[2, i])
        d = L.dense[i]
        pts = np.asarray(s["points"])
        a.fill(np.r_[d[:, 0], 0], np.r_[d[:, 1], d[0, 1]], color="#2f62d0", alpha=0.25)
        a.plot(d[:, 0], d[:, 1], color="k", lw=1)
        a.plot(pts[:, 0], pts[:, 1], "o", ms=2.5, color="#d04a2f")
        a.axvline(0, color="k", lw=3)
        a.set_xlim(-1.5, zmax); a.set_ylim(ylo, yhi); a.set_aspect("equal")
        a.tick_params(labelsize=7); a.grid(alpha=0.25)
        a.set_title(f"x = {s['x']:g}" + (f"\n{s['note']}" if s.get("note") else ""), fontsize=8)
    fig.suptitle(f"{spec['name']}  -  spec sheet", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
