// Centripetal Catmull-Rom splines through control points: the same curves as holdgen/curves.py.
// The client only evaluates curves for drawing and hit-testing; all lofting happens on the server.
// curves.test.ts checks these against golden output from the Python implementation.

export type Vec2 = [number, number];

function crSegment(p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2, n: number, out: Vec2[]): void {
  const tj = (ti: number, a: Vec2, b: Vec2) => ti + Math.sqrt(Math.max(Math.hypot(b[0] - a[0], b[1] - a[1]), 1e-9));
  const t0 = 0, t1 = tj(t0, p0, p1), t2 = tj(t1, p1, p2), t3 = tj(t2, p2, p3);
  const mix = (a: Vec2, b: Vec2, ta: number, tb: number, t: number): Vec2 => [
    ((tb - t) * a[0] + (t - ta) * b[0]) / (tb - ta),
    ((tb - t) * a[1] + (t - ta) * b[1]) / (tb - ta),
  ];
  for (let i = 0; i < n; i++) {
    const t = t1 + ((t2 - t1) * i) / n;
    const a1 = mix(p0, p1, t0, t1, t), a2 = mix(p1, p2, t1, t2, t), a3 = mix(p2, p3, t2, t3, t);
    const b1 = mix(a1, a2, t0, t2, t), b2 = mix(a2, a3, t1, t3, t);
    out.push(mix(b1, b2, t1, t2, t));
  }
}

const reflect = (a: Vec2, b: Vec2): Vec2 => [2 * a[0] - b[0], 2 * a[1] - b[1]];
const segCount = (a: Vec2, b: Vec2, step: number) => Math.max(4, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / step));

function openPiece(P: Vec2[], step: number): { dense: Vec2[]; idx: number[] } {
  const n = P.length;
  if (n === 1) return { dense: [[P[0][0], P[0][1]]], idx: [0] };
  const ext: Vec2[] = [reflect(P[0], P[1]), ...P, reflect(P[n - 1], P[n - 2])];
  const dense: Vec2[] = [], idx: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    idx.push(dense.length);
    crSegment(ext[i], ext[i + 1], ext[i + 2], ext[i + 3], segCount(P[i], P[i + 1], step), dense);
  }
  idx.push(dense.length);
  dense.push([P[n - 1][0], P[n - 1][1]]);
  return { dense, idx };
}

/** Dense polyline through an open curve; corners split the spline (position kept, tangent broken).
 *  dense[idx[i]] === points[i]. */
export function evalOpen(points: Vec2[], corners: number[] = [], step = 0.02): { dense: Vec2[]; idx: number[] } {
  const n = points.length;
  const cuts = [...new Set(corners.filter((c) => c > 0 && c < n - 1))].sort((a, b) => a - b);
  const bounds = [0, ...cuts, n - 1];
  let dense: Vec2[] = [];
  let idx: number[] = [];
  for (let k = 0; k < bounds.length - 1; k++) {
    let { dense: d, idx: ii } = openPiece(points.slice(bounds[k], bounds[k + 1] + 1), step);
    if (dense.length) {
      d = d.slice(1);
      ii = ii.slice(1).map((v) => v - 1);
    }
    const off = dense.length;
    dense = dense.concat(d);
    idx = idx.concat(ii.map((v) => v + off));
  }
  return { dense, idx };
}

/** Dense closed polyline (the last control point joins the first). */
export function evalClosed(points: Vec2[], corners: number[] = [], step = 0.02): Vec2[] {
  const n = points.length;
  if (n < 3) throw new Error("a closed curve needs at least 3 points");
  const cs = new Set(corners.map((c) => ((c % n) + n) % n));
  const out: Vec2[] = [];
  for (let i = 0; i < n; i++) {
    let p0 = points[(i - 1 + n) % n];
    const p1 = points[i], p2 = points[(i + 1) % n];
    let p3 = points[(i + 2) % n];
    if (cs.has(i)) p0 = reflect(p1, p2);
    if (cs.has((i + 1) % n)) p3 = reflect(p2, p1);
    crSegment(p0, p1, p2, p3, segCount(p1, p2, step), out);
  }
  return out;
}

export function arclen(poly: Vec2[]): number[] {
  const s = [0];
  for (let i = 1; i < poly.length; i++) s.push(s[i - 1] + Math.hypot(poly[i][0] - poly[i - 1][0], poly[i][1] - poly[i - 1][1]));
  return s;
}

/** Nearest segment of a polyline (or polygon) to w: the index to insert a new vertex at, and the distance. */
export function nearestSegment(points: Vec2[], w: Vec2, closed: boolean): { index: number; dist: number } {
  let best = 0, bd = Infinity;
  const n = points.length;
  for (let i = 0; i < (closed ? n : n - 1); i++) {
    const a = points[i], b = points[(i + 1) % n];
    const ab: Vec2 = [b[0] - a[0], b[1] - a[1]];
    const L2 = ab[0] ** 2 + ab[1] ** 2 || 1;
    const t = Math.max(0, Math.min(1, ((w[0] - a[0]) * ab[0] + (w[1] - a[1]) * ab[1]) / L2));
    const d = Math.hypot(a[0] + t * ab[0] - w[0], a[1] + t * ab[1] - w[1]);
    if (d < bd) {
      bd = d;
      best = i + 1;
    }
  }
  return { index: best, dist: bd };
}
