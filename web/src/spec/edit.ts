// Pure editing operations on an EditableSpec. They mutate the objects they're given; the store
// snapshots before/after for undo. Kept free of DOM and canvas code so they're unit tested.
import { arclen, evalOpen, type Vec2 } from "../geometry/curves";
import { ROOTS, type EditableSpec, type EStation } from "./model";

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
