"""Loft drawn cross-sections along x, with the optional front/top views as loose guides.

Rules (in priority order):
1. At every station the section is exactly the drawn spline.
2. Between stations, matched points (same landmark segment, same arc-length fraction)
   are blended with PCHIP, which passes through every station without overshoot.
3. The front view (x, y) and top view (x, z) may only change the shape *between*
   and *beyond* stations. Their correction is forced to zero at every station and
   scaled by each view's `strength`.
4. Beyond the outermost stations the views drive the taper into the tips. With no
   view extending past a station, the hold ends there with a rounded cap.
"""
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter1d

from . import curves


def _front_poly(view):
    """Closed outline from the upper and lower edges: upper left to right, then lower back to the left
    tip. The tips are corners (each edge is its own spline)."""
    up, _ = curves.eval_open(view["upper"])
    lo, _ = curves.eval_open(view["lower"])
    return np.vstack([up, lo[::-1][1:-1]])


def _top_poly(view):
    """Open curve from wall to wall; closed implicitly along the wall line (z = 0)."""
    dense, _ = curves.eval_open(view["points"], view.get("corners", []))
    return dense


def _extents(poly, xq):
    """Lowest and highest crossing of each vertical line x = xq with a closed polygon.

    Edge (a, b) is hit by x when min(ax, bx) <= x < max(ax, bx). Each edge's hits are a
    contiguous run of the sorted queries, so we scatter per edge: O(edges + crossings)."""
    xq = np.asarray(xq, float)
    order = np.argsort(xq, kind="stable")
    xs = xq[order]
    a, b = poly, np.roll(poly, -1, axis=0)
    lo_x, hi_x = np.minimum(a[:, 0], b[:, 0]), np.maximum(a[:, 0], b[:, 0])
    i0 = np.searchsorted(xs, lo_x, "left")
    i1 = np.searchsorted(xs, hi_x, "left")
    cnt = np.maximum(i1 - i0, 0)
    lo = np.full(len(xq), np.inf)
    hi = np.full(len(xq), -np.inf)
    total = int(cnt.sum())
    if total:
        e = np.repeat(np.arange(len(a)), cnt)
        q = np.arange(total) - np.repeat(np.cumsum(cnt) - cnt, cnt) + np.repeat(i0, cnt)
        dx = b[e, 0] - a[e, 0]
        y = a[e, 1] + (xs[q] - a[e, 0]) / dx * (b[e, 1] - a[e, 1])
        np.minimum.at(lo, q, y)
        np.maximum.at(hi, q, y)
    out_lo, out_hi = np.empty(len(xq)), np.empty(len(xq))
    out_lo[order], out_hi[order] = lo, hi
    out_lo[~np.isfinite(out_lo)] = np.nan
    out_hi[~np.isfinite(out_hi)] = np.nan
    return out_lo, out_hi


def _extents_dense(poly, xq):
    """Reference O(queries x edges) implementation, kept for tests."""
    a = poly
    b = np.roll(poly, -1, axis=0)
    x0, x1 = a[:, 0][None], b[:, 0][None]
    X = np.asarray(xq, float)[:, None]
    hit = ((x0 <= X) & (X < x1)) | ((x1 <= X) & (X < x0))
    t = (X - x0) / np.where(x1 == x0, 1, x1 - x0)
    yv = a[:, 1][None] + t * (b[:, 1] - a[:, 1])[None]
    lo = np.where(hit, yv, np.inf).min(1)
    hi = np.where(hit, yv, -np.inf).max(1)
    lo[~np.isfinite(lo)] = np.nan
    hi[~np.isfinite(hi)] = np.nan
    return lo, hi


class Loft:
    def __init__(self, spec):
        self.spec = spec
        st = spec["stations"]
        step = spec["build"]["sample_step"]
        self.xs = np.array([s["x"] for s in st], float)
        names = spec["landmark_order"]
        dense, segs = [], []
        for s in st:
            d, ci = curves.eval_open(s["points"], s.get("corners", []))
            cut = [ci[s["landmarks"][k]] for k in names]
            pieces = [d[a:b + 1] for a, b in zip(cut[:-1], cut[1:])]
            dense.append(d)
            segs.append(pieces)
        self.dense = dense                              # exact drawn curves, per station
        nseg = len(names) - 1
        counts = [int(np.ceil(max(curves.arclen(segs[i][k])[-1] for i in range(len(st))) / step)) + 1
                  for k in range(nseg)]
        rows = []
        for i in range(len(st)):
            parts = [curves.resample(segs[i][k], counts[k]) for k in range(nseg)]
            row = parts[0]
            for p in parts[1:]:
                row = np.vstack([row, p[1:]])
            rows.append(row)
        self.M = np.stack(rows)                         # (stations, N, 2) as [z, y]
        self.landmark_index = dict(zip(names, np.concatenate([[0], np.cumsum(np.array(counts) - 1)])))
        self._pchip = PchipInterpolator(self.xs, self.M.reshape(len(st), -1), axis=0)

        self.front = _front_poly(spec["front_view"]) if spec["front_view"] else None
        self.top = _top_poly(spec["top_view"]) if spec["top_view"] else None
        self._prep_guides()
        self._prep_tips()

    # ------------------------------------------------------------------ guides
    def _pinned_residual(self, view_poly, which, measure):
        """Correction p(x) = (view - lofted), minus its own interpolant through the station values,
        lightly smoothed. Returns a callable that is exactly zero at every station (the pin is
        applied at query time, so no grid interpolation can leak into a station)."""
        xf = np.linspace(self.xs[0], self.xs[-1], int(np.ceil((self.xs[-1] - self.xs[0]) / 0.1)) + 1)  # ends exactly on the outer stations
        B = self._pchip(xf).reshape(len(xf), -1, 2)
        lo, hi = _extents(view_poly, xf)
        target = lo if which == "lo" else hi
        r = target - measure(B)
        lo_s, hi_s = _extents(view_poly, self.xs)
        tst = lo_s if which == "lo" else hi_s
        r_st = np.nan_to_num(tst - measure(self.M))
        base = PchipInterpolator(self.xs, r_st)(xf)
        r = np.where(np.isnan(r), base, r)
        p = gaussian_filter1d(r - base, sigma=20, mode="nearest")     # 2 mm
        pin = PchipInterpolator(self.xs, np.interp(self.xs, xf, p))    # C1, passes through p at stations

        def corr(x):
            x = np.asarray(x, float)
            return np.interp(x, xf, p) - pin(x)
        return corr

    def _prep_guides(self):
        self.g_front = self.g_top = None
        ylo = lambda B: B[..., 1].min(-1)
        yhi = lambda B: B[..., 1].max(-1)
        zhi = lambda B: B[..., 0].max(-1)
        if self.front is not None:
            self.g_front = (self._pinned_residual(self.front, "lo", ylo),
                            self._pinned_residual(self.front, "hi", yhi), self.spec["front_view"]["strength"])
        if self.top is not None:
            self.g_top = (self._pinned_residual(self.top, "hi", zhi), self.spec["top_view"]["strength"])

    def _body(self, xq):
        """Blended sections between the outermost stations, with the view corrections applied."""
        xq = np.asarray(xq, float)
        B = self._pchip(xq).reshape(len(xq), -1, 2)
        if self.g_front is not None:
            plo, phi, g = self.g_front
            lo, hi = B[..., 1].min(1, keepdims=True), B[..., 1].max(1, keepdims=True)
            a, b = plo(xq)[:, None], phi(xq)[:, None]
            t = (B[..., 1] - lo) / (hi - lo)
            B[..., 1] += g * (a + (b - a) * t)
        if self.g_top is not None:
            pz, g = self.g_top
            zh = B[..., 0].max(1, keepdims=True)
            B[..., 0] *= np.clip(1 + g * pz(xq)[:, None] / zh, 0.05, None)
        return B

    # ------------------------------------------------------------------ tips
    def _prep_tips(self):
        self.tip = {}
        for side, xe, sgn in (("left", self.xs[0], -1), ("right", self.xs[-1], 1)):
            driver, xt = None, None
            for name, poly in (("front", self.front), ("top", self.top)):
                if poly is None:
                    continue
                ext = poly[:, 0].min() if sgn < 0 else poly[:, 0].max()
                if (ext - xe) * sgn > 0.5:
                    driver, xt = name, ext
                    break
            if driver is None:
                self.tip[side] = {"kind": "cap", "x_end": xe,
                                  "radius": float(self.spec["end_caps"]["radius"])}
            else:
                self.tip[side] = {"kind": "taper", "x_end": xe, "x_tip": xt, "driver": driver}
        lt, rt = self.tip["left"], self.tip["right"]
        self.x_min = lt["x_tip"] if lt["kind"] == "taper" else lt["x_end"]
        self.x_max = rt["x_tip"] if rt["kind"] == "taper" else rt["x_end"]

    def _taper(self, xq, side):
        info = self.tip[side]
        i = 0 if side == "left" else -1
        E = self.M[i]
        xe, xt = info["x_end"], info["x_tip"]
        u = np.clip((xq - xe) / (xt - xe), 0, 1)[:, None]
        lo_e, hi_e = E[:, 1].min(), E[:, 1].max()
        zh_e = E[:, 0].max()
        out = np.repeat(E[None], len(xq), 0).copy()
        ratio_h = None
        if self.front is not None:
            olo_e, ohi_e = _extents(self.front, [xe])
            olo_e = lo_e if np.isnan(olo_e[0]) else olo_e[0]
            ohi_e = hi_e if np.isnan(ohi_e[0]) else ohi_e[0]
            olo, ohi = _extents(self.front, xq)
            tip_y = self.front[np.argmin(self.front[:, 0]) if side == "left" else np.argmax(self.front[:, 0]), 1]
            olo = np.where(np.isnan(olo), tip_y, olo)[:, None]
            ohi = np.where(np.isnan(ohi), tip_y, ohi)[:, None]
            tlo = olo - (olo_e - lo_e) * (1 - u)
            thi = np.maximum(ohi - (ohi_e - hi_e) * (1 - u), tlo)
            out[..., 1] = tlo + (E[None, :, 1] - lo_e) / (hi_e - lo_e) * (thi - tlo)
            ratio_h = ((thi - tlo) / (hi_e - lo_e))
        if self.top is not None:
            _, oz_e = _extents(self.top, [xe])
            oz_e = zh_e if np.isnan(oz_e[0]) else oz_e[0]
            _, oz = _extents(self.top, xq)
            tz = np.maximum(np.nan_to_num(oz, nan=0.0)[:, None] - (oz_e - zh_e) * (1 - u), 0)
            rz = tz / zh_e
        else:
            rz = np.clip(ratio_h, 0, None) ** 0.7
        out[..., 0] = E[None, :, 0] * rz
        if self.front is None:                              # top view only: shrink y about the middle
            c = 0.5 * (lo_e + hi_e)
            out[..., 1] = c + (E[None, :, 1] - c) * rz
        # Leave the end station along the guided body's own slope (no crease): blend from the body's
        # linear continuation into the view-driven taper over the first half of the tip. The slope is a
        # second-order one-sided difference taken inside the body.
        d, dl = (1.0 if side == "left" else -1.0), 0.02
        f0, f1, f2 = self._body([xe, xe + d * dl, xe + 2 * d * dl])
        dM = (-3 * f0 + 4 * f1 - f2) / (2 * d * dl)
        ext = E[None] + (xq - xe)[:, None, None] * dM[None]
        ext[..., 0] = np.maximum(ext[..., 0], 0)
        s = np.clip(u / 0.5, 0, 1)[..., None]
        w = s * s * (3 - 2 * s)
        return ext * (1 - w) + out * w

    # ------------------------------------------------------------------ public
    def at(self, xq):
        """Lofted sections at xq. Returns (polys (n, N, 2) [z, y], valid mask (n,)).
        Rounded caps are not included here (see sdf.build)."""
        xq = np.asarray(xq, float)
        out = np.zeros((len(xq), self.M.shape[1], 2))
        valid = np.zeros(len(xq), bool)
        body = (xq >= self.xs[0]) & (xq <= self.xs[-1])
        if body.any():
            out[body] = self._body(xq[body])
            valid[body] = True
        for side in ("left", "right"):
            if self.tip[side]["kind"] != "taper":
                continue
            m = (xq < self.xs[0]) if side == "left" else (xq > self.xs[-1])
            m &= (xq >= self.x_min) & (xq <= self.x_max)
            if m.any():
                T = self._taper(xq[m], side)
                ok = (np.ptp(T[..., 1], axis=1) > 0.2) & (T[..., 0].max(1) > 0.2)
                out[np.nonzero(m)[0][ok]] = T[ok]
                valid[np.nonzero(m)[0][ok]] = True
        return out, valid
