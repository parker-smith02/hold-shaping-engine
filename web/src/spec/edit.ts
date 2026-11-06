// Pure editing operations on an EditableSpec. They mutate the objects they're given; the store
// snapshots before/after for undo. Kept free of DOM and canvas code so they're unit tested.
import { arclen, evalOpen, type Vec2 } from "../geometry/curves";
import { ROOTS, type EditableSpec, type EFront, type EStation, type ETop } from "./model";

export function landmarkOrder(st: EStation): [string, number][] {
  const lm: Record<string, number> = { ...st.landmarks, bottom_root: 0, ledge_root: st.points.length - 1 };
  return Object.entries(lm).sort((a, b) => a[1] - b[1]);
}

/** Landmark names used anywhere in the spec (excluding the implicit roots), first-seen order. */
export function landmarkNames(spec: EditableSpec): string[] {
  const seen = new Set<string>();
  for (const st of spec.stations) for (const [k] of landmarkOrder(st)) if (!(ROOTS as readonly string[]).includes(k)) seen.add(k);
  return [...seen];
}

export function isRoot(st: EStation, i: number): boolean {
  return i === 0 || i === st.points.length - 1;
}

export function insertPoint(st: EStation, at: number, p: Vec2): void {
  st.points.splice(at, 0, [Math.max(0, p[0]), p[1]]);
  for (const k in st.landmarks) if (st.landmarks[k] >= at) st.landmarks[k]++;
  st.corners = st.corners.map((c) => (c >= at ? c + 1 : c));
}

export type Refusal = { ok: false; reason: string };
export type Result = { ok: true } | Refusal;

export function removePoint(st: EStation, i: number): Result {
  if (isRoot(st, i)) return { ok: false, reason: "The wall roots can't be removed. Drag them along the wall instead." };
  if (Object.values(st.landmarks).includes(i)) return { ok: false, reason: "This point is a landmark. Move the landmark to another point first." };
  if (st.points.length <= 3) return { ok: false, reason: "A section needs at least three points." };
  st.points.splice(i, 1);
  for (const k in st.landmarks) if (st.landmarks[k] > i) st.landmarks[k]--;
  st.corners = st.corners.filter((c) => c !== i).map((c) => (c > i ? c - 1 : c));
  return { ok: true };
}

export function toggleCorner(st: EStation, i: number): void {
  if (isRoot(st, i)) return;
  st.corners = st.corners.includes(i) ? st.corners.filter((c) => c !== i) : [...st.corners, i].sort((a, b) => a - b);
}

/** Move a point, keeping wall roots on the wall and everything in front of it. */
export function movePoint(st: EStation, i: number, p: Vec2): void {
  st.points[i] = [isRoot(st, i) ? 0 : Math.max(0, p[0]), p[1]];
}

/** Assign `name` to point i of `st` (removing any other landmark on that point). */
export function setLandmark(st: EStation, i: number, name: string | null): void {
  for (const k of Object.keys(st.landmarks)) if (st.landmarks[k] === i || k === name) delete st.landmarks[k];
  if (name) st.landmarks[name] = i;
}

/** Heuristic landmark placement for a freshly drawn section: lip_apex = highest point,
 *  face_out = outermost point, anything else = first free interior point. */
export function autoLandmarks(points: Vec2[], names: string[]): Record<string, number> {
  const n = points.length, lm: Record<string, number> = {};
  let iy = 1, iz = 1;
  for (let i = 1; i < n - 1; i++) {
    if (points[i][1] > points[iy][1]) iy = i;
    if (points[i][0] > points[iz][0]) iz = i;
  }
  const taken = new Set([0, n - 1]);
  for (const nm of names) {
    let i = nm === "lip_apex" ? iy : nm === "face_out" ? iz : -1;
    if (i < 0 || taken.has(i)) {
      i = 1;
      while (taken.has(i) && i < n - 2) i++;
    }
    lm[nm] = i;
    taken.add(i);
  }
  return lm;
}

/** Give every other station landmark `name` at the same arc-length fraction as point i of `src`:
 *  reuse a free control point within `snap` mm, otherwise insert one on the curve. */
export function placeLandmarkEverywhere(spec: EditableSpec, name: string, src: EStation, i: number, snap = 1.5): void {
  const d0 = evalOpen(src.points, src.corners, 0.05);
  const s0 = arclen(d0.dense);
  const f = s0[d0.idx[i]] / s0[s0.length - 1];
  for (const st of spec.stations) {
    if (st === src || name in st.landmarks) continue;
    const { dense, idx } = evalOpen(st.points, st.corners, 0.05);
    const s = arclen(dense), L = s[s.length - 1];
    let k = 0;
    while (k < s.length - 1 && s[k] < f * L) k++;
    const taken = new Set([...Object.values(st.landmarks), 0, st.points.length - 1]);
    let best = -1, bd = Infinity;
    idx.forEach((di, ci) => {
      const dd = Math.abs(s[di] - s[k]);
      if (!taken.has(ci) && dd < bd) {
        bd = dd;
        best = ci;
      }
    });
    if (best >= 0 && bd < snap) st.landmarks[name] = best;
    else {
      let span = 0;
      while (span < idx.length - 1 && idx[span + 1] <= k) span++;
      insertPoint(st, span + 1, dense[k]);
      st.landmarks[name] = span + 1;
    }
  }
}

/** Sort stations by x; returns the new index of `track` (e.g. the selected station). */
export function sortStations(spec: EditableSpec, track?: EStation): number {
  spec.stations.sort((a, b) => a.x - b.x);
  return track ? spec.stations.indexOf(track) : -1;
}

export function stationExtent(st: EStation): { yLo: number; yHi: number; zHi: number } {
  const { dense } = evalOpen(st.points, st.corners, 0.25);
  let yLo = Infinity, yHi = -Infinity, zHi = 0;
  for (const [z, y] of dense) {
    yLo = Math.min(yLo, y);
    yHi = Math.max(yHi, y);
    zHi = Math.max(zHi, z);
  }
  return { yLo, yHi, zHi };
}

// ------------------------------------------------------------------ loose views (front, top)

export type Edge = "upper" | "lower";
/** Minimum x gap (mm) between a tip or wall end and any point between them. */
export const TIP_GAP = 1;

/** x range a new outline spans: the stations plus a margin for the tips, or a default with no stations. */
export function outlineSpan(spec: EditableSpec): [number, number] {
  if (!spec.stations.length) return [-50, 50];
  const xs = spec.stations.map((s) => s.x), a = Math.min(...xs), b = Math.max(...xs);
  const pad = Math.max(15, 0.2 * (b - a));
  return [a - pad, b + pad];
}

/** Station extents linearly interpolated at x (held flat beyond the outer stations), or null with none. */
export function extentAt(spec: EditableSpec, x: number): { yLo: number; yHi: number; zHi: number } | null {
  const st = [...spec.stations].sort((a, b) => a.x - b.x);
  if (!st.length) return null;
  const ext = st.map(stationExtent);
  if (x <= st[0].x) return ext[0];
  if (x >= st[st.length - 1].x) return ext[ext.length - 1];
  let k = 0;
  while (st[k + 1].x < x) k++;
  const u = (x - st[k].x) / (st[k + 1].x - st[k].x), a = ext[k], b = ext[k + 1];
  return { yLo: a.yLo + u * (b.yLo - a.yLo), yHi: a.yHi + u * (b.yHi - a.yHi), zHi: a.zHi + u * (b.zHi - a.zHi) };
}

const r1 = (v: number) => Math.round(v * 10) / 10;

/** A front outline around the current stations: tips beyond the outer stations at mid height, three
 *  points on each edge following the stations' top and bottom. A starting point to drag, not a guess. */
export function defaultFrontView(spec: EditableSpec): EFront {
  const [x0, x1] = outlineSpan(spec);
  const e0 = extentAt(spec, x0) ?? { yLo: 10, yHi: 50, zHi: 20 }, e1 = extentAt(spec, x1) ?? e0;
  const tipL: Vec2 = [r1(x0), r1((e0.yLo + e0.yHi) / 2)], tipR: Vec2 = [r1(x1), r1((e1.yLo + e1.yHi) / 2)];
  const xs = [0.25, 0.5, 0.75].map((f) => x0 + f * (x1 - x0));
  const at = (x: number) => extentAt(spec, x) ?? e0;
  return {
    upper: [tipL, ...xs.map((x): Vec2 => [r1(x), r1(at(x).yHi)]), tipR],
    lower: [tipL, ...xs.map((x): Vec2 => [r1(x), r1(at(x).yLo)]), tipR],
    strength: 0.5,
  };
}

/** A top outline around the current stations: wall to wall, three points following the stations' depth. */
export function defaultTopView(spec: EditableSpec): ETop {
  const [x0, x1] = outlineSpan(spec);
  const xs = [0.25, 0.5, 0.75].map((f) => x0 + f * (x1 - x0));
  return {
    points: [[r1(x0), 0], ...xs.map((x): Vec2 => [r1(x), r1(extentAt(spec, x)?.zHi ?? 20)]), [r1(x1), 0]],
    strength: 0.5,
    corners: [],
  };
}

const interiorXs = (curves: Vec2[][]) => curves.flatMap((P) => P.slice(1, -1).map((q) => q[0]));

/** Clamp an end point's x so it stays outside every interior point and on its own side of the other end. */
function clampEnd(x: number, left: boolean, inner: number[], other: number): number {
  if (left) return Math.min(x, (inner.length ? Math.min(...inner) : other) - TIP_GAP);
  return Math.max(x, (inner.length ? Math.max(...inner) : other) + TIP_GAP);
}

/** Move point i of a front edge. A tip moves on both edges; points between the tips stay between them. */
export function moveFrontPoint(fv: EFront, edge: Edge, i: number, p: Vec2): void {
  const P = fv[edge], n = P.length;
  if (i === 0 || i === n - 1) {
    const left = i === 0, other = left ? fv.upper[n - 1][0] : fv.upper[0][0];
    const q: Vec2 = [clampEnd(p[0], left, interiorXs([fv.upper, fv.lower]), other), p[1]];
    for (const E of [fv.upper, fv.lower]) E[left ? 0 : E.length - 1] = [q[0], q[1]];
    return;
  }
  const a = fv.upper[0][0] + TIP_GAP, b = fv.upper[fv.upper.length - 1][0] - TIP_GAP;
  P[i] = [Math.min(b, Math.max(a, p[0])), p[1]];
}

/** Move point i of the top view. The ends slide along the wall; the rest stay between them, off the wall side. */
export function moveTopPoint(tv: ETop, i: number, p: Vec2): void {
  const P = tv.points, n = P.length;
  if (i === 0 || i === n - 1) {
    const left = i === 0;
    P[i] = [clampEnd(p[0], left, interiorXs([P]), left ? P[n - 1][0] : P[0][0]), 0];
    return;
  }
  P[i] = [Math.min(P[n - 1][0] - TIP_GAP, Math.max(P[0][0] + TIP_GAP, p[0])), Math.max(0, p[1])];
}

/** Where a click at w lands on an open curve: the span it falls in and the point on the curve.
 *  `dist` is in mm; callers compare it against a pixel tolerance. */
export function nearestOnCurve(P: Vec2[], corners: number[], w: Vec2): { index: number; point: Vec2; dist: number } {
  const { dense, idx } = evalOpen(P, corners, 0.1);
  let bi = 0, bd = Infinity;
  dense.forEach((q, i) => {
    const d = Math.hypot(q[0] - w[0], q[1] - w[1]);
    if (d < bd) {
      bd = d;
      bi = i;
    }
  });
  let k = 0;
  while (k < idx.length - 2 && idx[k + 1] <= bi) k++;
  return { index: k + 1, point: [dense[bi][0], dense[bi][1]], dist: bd };
}

/** Insert p before index `at` of an open curve (never before the first or after the last point). */
export function insertCurvePoint(P: Vec2[], at: number, p: Vec2, corners?: number[]): number {
  const k = Math.max(1, Math.min(P.length - 1, at));
  P.splice(k, 0, [p[0], p[1]]);
  if (corners) corners.splice(0, corners.length, ...corners.map((c) => (c >= k ? c + 1 : c)));
  return k;
}

/** Remove an interior point of an open outline curve. The ends (tips, wall ends) stay. */
export function removeCurvePoint(P: Vec2[], i: number, corners?: number[]): Result {
  if (i === 0 || i === P.length - 1) return { ok: false, reason: "The ends of an outline can't be removed; drag them instead, or clear the view." };
  P.splice(i, 1);
  if (corners) corners.splice(0, corners.length, ...corners.filter((c) => c !== i).map((c) => (c > i ? c - 1 : c)));
  return { ok: true };
}
