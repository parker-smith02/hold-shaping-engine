import { describe, expect, it } from "vitest";
import golden from "./curves.golden.json";
import { arclen, evalClosed, evalOpen, nearestSegment, type Vec2 } from "./curves";

type Case = { name: string; kind: "open" | "closed"; points: Vec2[]; corners: number[]; step: number; dense: Vec2[]; idx?: number[] };

const maxDiff = (a: Vec2[], b: Vec2[]) => Math.max(...a.map((p, i) => Math.hypot(p[0] - b[i][0], p[1] - b[i][1])));

describe("curves match holdgen/curves.py (golden output)", () => {
  for (const c of (golden as { cases: Case[] }).cases) {
    it(c.name, () => {
      if (c.kind === "open") {
        const { dense, idx } = evalOpen(c.points, c.corners, c.step);
        expect(dense.length).toBe(c.dense.length);
        expect(idx).toEqual(c.idx);
        expect(maxDiff(dense, c.dense)).toBeLessThan(1e-9);
      } else {
        const dense = evalClosed(c.points, c.corners, c.step);
        expect(dense.length).toBe(c.dense.length);
        expect(maxDiff(dense, c.dense)).toBeLessThan(1e-9);
      }
    });
  }
});

describe("curve properties", () => {
  const pts: Vec2[] = [[0, 0], [6, 12], [10, 25], [7, 31], [0, 29]];

  it("passes through every control point", () => {
    const { dense, idx } = evalOpen(pts, [], 0.1);
    idx.forEach((di, i) => expect(Math.hypot(dense[di][0] - pts[i][0], dense[di][1] - pts[i][1])).toBeLessThan(1e-12));
  });

  it("breaks the tangent at a corner but not elsewhere", () => {
    const turn = (corners: number[]) => {
      const { dense, idx } = evalOpen(pts, corners, 0.01);
      const k = idx[2], a = dense[k - 1], b = dense[k], c = dense[k + 1];
      const t1 = Math.atan2(b[1] - a[1], b[0] - a[0]), t2 = Math.atan2(c[1] - b[1], c[0] - b[0]);
      return Math.abs(t2 - t1);
    };
    expect(turn([])).toBeLessThan(0.01);
    expect(turn([2])).toBeGreaterThan(0.1);
  });

  it("arclen is monotone and nearestSegment finds the inserting span", () => {
    const s = arclen(pts);
    for (let i = 1; i < s.length; i++) expect(s[i]).toBeGreaterThan(s[i - 1]);
    expect(nearestSegment(pts, [8.2, 18], false).index).toBe(2);
  });
});
