"""
Ravage-inspired 25 mm incut crimp - smooth blank for sanding / molding.
Leaf/lens outline with tapered pointed ends, slight banana curve, deep incut ledge
along the top with a large rounded lip, two countersunk screw holes.

Frame (mm): x along the edge, y up the wall, z out of the wall (z=0 = flat back).
"""
import numpy as np, os, sys
from scipy import ndimage

VOX = 0.30
T_PEAK = float(os.environ.get("T_PEAK", 20.6))              # hold thickness at the lip, middle
T_END = 2.5
R_LIP_MAX = float(os.environ.get("R_LIP", 6.5))
XL, XR = -80.0, 82.0                                        # tip positions
LT_L, LT_R = 55.0, 66.0                                     # taper lengths (right end longer/pointier)

def q(t):            # rises ~linearly from 0 (pointed tip), eases to a flat 1
    t = np.clip(t, 0, 1)
    return 1 - (1 - t) ** 2

def P(x):            # 0 at tips -> 1 across the middle ~half
    return q((x - XL) / LT_L) * q((XR - x) / LT_R)

def y_root(x):       # where the ledge meets the wall: gentle banana + dished middle
    w = 1 - P(x)
    return 58.0 + 6.0 * w * (1 - w) - 13.0 * w ** 1.6      # slight dish, then rolls down into the tips

def H_body(x):       # wall-line to bottom outline (front view height of the body below the edge)
    return 42.0 * P(x) ** 0.85 + 3.0 * np.exp(-((x + 25) / 22) ** 2) * P(x)

def T_lip(x):
    return T_END + (T_PEAK - T_END) * P(x)

# ---------------------------------------------------------------- grid
xs = np.arange(-88, 90, VOX, dtype=np.float32)
ys = np.arange(4, 86, VOX, dtype=np.float32)
zs = np.arange(-1.0 + VOX * 0.5, 30, VOX, dtype=np.float32)
nx, ny, nz = len(xs), len(ys), len(zs)
print("grid", nx, ny, nz, round(nx * ny * nz / 1e6, 1), "M", file=sys.stderr)
X2, Y2 = np.meshgrid(xs, ys, indexing="ij")
x1 = xs.astype(np.float64)
yr = y_root(x1)[:, None]; Hb = H_body(x1)[:, None]; yb = yr - Hb
Tl = T_lip(x1)[:, None]; Px = P(x1)[:, None]

# ---------------- front face height F(x, y): convex wedge from bottom edge up to the lip
s = np.clip((Y2 - yb) / np.maximum(Hb, 3.0), 0, None)
g = 1 - (1 - np.clip(s, 0, 1)) ** 1.8
TB = 2.5
F = TB + (Tl - TB) * g
# soft diagonal flute across the face (nod to the Ravage facet lines), fades out near lip & tips
u = (X2 - 18.0) - 0.9 * (Y2 - 30.0)
F = F - 0.7 * np.exp(-(u / 8.0) ** 2) * np.clip(1.0 - s, 0, 1) * np.clip(s / 0.25, 0, 1) * Px
# slight extra belly mid-face on the left half for some asymmetry
F = F + 1.0 * np.exp(-(((X2 + 30) / 26) ** 2 + ((s - 0.55) / 0.25) ** 2))
# fuller, slightly bulbous lip
F = F + 1.2 * Px * np.exp(-((s - 1.15) / 0.22) ** 2)
F = ndimage.gaussian_filter(F, 3)
Fx, Fy = np.gradient(F, VOX, VOX)
Fn = np.sqrt(1 + Fx ** 2 + Fy ** 2).astype(np.float32)
F = F.astype(np.float32)

# ---------------- 2D outline (bottom + ends), with rounded tips
top_ext = yr + 30.0 * Px ** 0.7                      # well above the ledge; the ledge plane trims the top
mask = (Y2 > yb) & (Y2 < top_ext) & (X2 > XL) & (X2 < XR)
def sdf2(m):
    return (ndimage.distance_transform_edt(~m) - ndimage.distance_transform_edt(m)) * VOX
R_TIP = 5.0
d2 = sdf2(sdf2(mask) < -R_TIP) - R_TIP
d2 = ndimage.gaussian_filter(d2, 1.5).astype(np.float32)

def smax_c(a, b, r):
    return np.minimum(-r, np.maximum(a, b)) + np.sqrt(np.maximum(a + r, 0) ** 2 + np.maximum(b + r, 0) ** 2)

DRAFT = np.tan(np.radians(18))
R_LIP = (2.0 + (R_LIP_MAX - 2.0) * Px).astype(np.float32)
R_SIDE = 4.0
yrf = yr.astype(np.float32)

# ---- sculpted ledge surface  Yl(x, z) = root + a*z + b*z^2  (concave: shallow at the wall, hooking at the lip)
TH0_A, TH1_A = np.radians(16), np.radians(float(os.environ.get("TH1A", 62)))   # left of the fold: deep hook
TH0_B, TH1_B = np.radians(24), np.radians(float(os.environ.get("TH1B", 54)))   # right of the fold: rounder, less hooked
Tz = np.maximum(T_lip(x1), 4.0)                                               # lip position per x
def coeffs(t0, t1):
    a = np.tan(t0); b = (np.tan(t1) - np.tan(t0)) / (2 * Tz)
    return a, b
aA, bA = coeffs(TH0_A, TH1_A); aB, bB = coeffs(TH0_B, TH1_B)
def ledge_y(z):
    xf = 10.0 + 0.9 * z                                   # diagonal fold line across the ledge
    w = 1 / (1 + np.exp(-(x1 - xf) / 1.6))                # 0 = left facet, 1 = right facet (soft crease)
    yA = aA * z + bA * z * z
    yB = aB * z + bB * z * z + 1.5                        # right facet sits a touch higher -> visible step/fold
    Y = (1 - w) * yA + w * yB
    zz = np.minimum(z / Tz, 1.0)
    Y -= 2.3 * np.exp(-((x1 + 28) / 16) ** 2) * np.sin(np.pi * zz) * (z < Tz)   # thumb scoop, left of centre
    Y -= 1.3 * np.exp(-((x1 - 36) / 13) ** 2) * np.sin(np.pi * zz) * (z < Tz)   # smaller scoop, right
    return y_root(x1) + Y

S = np.empty((nx, ny, nz), np.float32)
for k, z in enumerate(zs):
    d_front = (z - F) / Fn
    Yl = ledge_y(z); dz = 0.15
    Yz = (ledge_y(z + dz) - ledge_y(z - dz)) / (2 * dz); Yx = np.gradient(Yl, VOX)
    d_ledge = ((Y2 - Yl[:, None]) / np.sqrt(1 + Yz ** 2 + Yx ** 2)[:, None]).astype(np.float32)
    d = smax_c(d_front, d_ledge, R_LIP)
    d = smax_c(d, d2 + z * DRAFT, R_SIDE)
    S[:, :, k] = np.maximum(d, -z)

# ---------------- two countersunk screw holes
Z3 = zs[None, None, :]
screws = []
for SX, frac in [(-40.0, 0.50), (42.0, 0.50)]:
    SY = float(y_root(np.array([SX]))[0] - (1 - frac) * H_body(np.array([SX]))[0])
    rs = np.sqrt((X2 - SX) ** 2 + (Y2 - SY) ** 2)[:, :, None]
    F_s = float(F[np.argmin(np.abs(xs - SX)), np.argmin(np.abs(ys - SY))])
    S = np.maximum(S, -(rs - (2.4 + np.maximum(Z3 - (F_s - 2.8), 0) * 1.0)))   # 4.8 mm + 90deg c-sink
    screws.append((SX, SY, F_s))

S = ndimage.gaussian_filter(S, 0.6)
S[0], S[-1] = 1, 1; S[:, 0], S[:, -1] = 1, 1; S[:, :, 0], S[:, :, -1] = 1, 1
np.save(__import__("os").path.dirname(__import__("os").path.abspath(__file__)) + "/sdf.npy", S)
np.savez(__import__("os").path.dirname(__import__("os").path.abspath(__file__)) + "/meta.npz", xs=xs, ys=ys, zs=zs)
for sx, sy, fs in screws:
    print("screw at (%.1f, %.1f)  face thickness %.1f mm" % (sx, sy, fs), file=sys.stderr)
