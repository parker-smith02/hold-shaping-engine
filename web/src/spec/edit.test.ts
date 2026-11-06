import { describe, expect, it } from "vitest";
import type { Vec2 } from "../geometry/curves";
import {
  autoLandmarks, defaultFrontView, defaultTopView, insertCurvePoint, insertPoint, landmarkNames, landmarkOrder, moveFrontPoint,
  movePoint, moveTopPoint, nearestOnCurve, placeLandmarkEverywhere, removeCurvePoint, removePoint, setLandmark, sortStations,
  stationExtent, TIP_GAP, toggleCorner,
} from "./edit";
import { EMPTY, fromSpec, toSpec, type EditableSpec, type EStation } from "./model";

const section = (): Vec2[] => [[0, 10], [7, 20], [12, 32], [13.5, 40], [11, 45], [6, 43.5], [0, 42]];
const station = (x = 0): EStation => ({ x, points: section(), landmarks: { lip_apex: 4 }, corners: [2], note: "" });
const spec = (): EditableSpec =>
  fromSpec({ schema: "hold-spec/1", name: "t", stations: [station(-30), station(0), station(30)] });

describe("point edits keep landmarks and corners attached to the same points", () => {
  it("insertPoint shifts indices at and after the insertion", () => {
    const st = station();
    insertPoint(st, 2, [9, 26]);
    expect(st.points[2]).toEqual([9, 26]);
    expect(st.landmarks.lip_apex).toBe(5);
    expect(st.corners).toEqual([3]);
  });

  it("removePoint refuses roots and landmarks, shifts the rest", () => {
    const st = station();
    expect(removePoint(st, 0).ok).toBe(false);
    expect(removePoint(st, 6).ok).toBe(false);
    expect(removePoint(st, 4).ok).toBe(false);
    expect(removePoint(st, 2)).toEqual({ ok: true });
    expect(st.corners).toEqual([]);
    expect(st.landmarks.lip_apex).toBe(3);
    expect(st.points[3]).toEqual([11, 45]);
  });

  it("movePoint pins roots to the wall and keeps points in front of it", () => {
    const st = station();
    movePoint(st, 0, [3, 8]);
    movePoint(st, 2, [-2, 30]);
    expect(st.points[0]).toEqual([0, 8]);
    expect(st.points[2]).toEqual([0, 30]);
  });

  it("toggleCorner ignores roots", () => {
    const st = station();
    toggleCorner(st, 0);
    toggleCorner(st, 3);
    expect(st.corners).toEqual([2, 3]);
    toggleCorner(st, 2);
    expect(st.corners).toEqual([3]);
  });
});

describe("landmarks", () => {
  it("landmarkOrder includes the implicit roots in curve order", () => {
    expect(landmarkOrder(station()).map(([k]) => k)).toEqual(["bottom_root", "lip_apex", "ledge_root"]);
  });

  it("setLandmark moves a name and clears what was on the point", () => {
    const st = station();
    setLandmark(st, 3, "lip_apex");
    expect(st.landmarks).toEqual({ lip_apex: 3 });
    setLandmark(st, 3, null);
    expect(st.landmarks).toEqual({});
  });

  it("autoLandmarks puts lip_apex at the highest point and face_out at the outermost", () => {
    expect(autoLandmarks(section(), ["face_out", "lip_apex"])).toEqual({ face_out: 3, lip_apex: 4 });
  });

  it("placeLandmarkEverywhere gives every station the landmark in a consistent order", () => {
    const s = spec();
    const src = s.stations[1];
    setLandmark(src, 2, "lip_start");
    placeLandmarkEverywhere(s, "lip_start", src, 2);
    expect(landmarkNames(s).sort()).toEqual(["lip_apex", "lip_start"]);
    for (const st of s.stations) {
      expect(st.landmarks.lip_start).toBeDefined();
      expect(landmarkOrder(st).map(([k]) => k)).toEqual(landmarkOrder(src).map(([k]) => k));
    }
  });
});

describe("spec round trip", () => {
  it("sortStations returns the tracked station's new index", () => {
    const s = spec();
    const moved = s.stations[0];
    moved.x = 50;
    expect(sortStations(s, moved)).toBe(2);
  });

  it("toSpec(fromSpec(x)) keeps geometry (rounded to 0.01 mm) and drops implicit roots", () => {
    const s = spec();
    s.stations[0].points[2] = [12.3456, 32.0049];
    const out = toSpec(s);
    expect(out.stations[0].points[2]).toEqual([12.35, 32]);
    expect(Object.keys(out.stations[0].landmarks ?? {})).toEqual(["lip_apex"]);
    expect(fromSpec(out).stations[0].points.length).toBe(7);
  });
});

describe("outlines are open curves bounded at their ends", () => {
  it("the default front view spans past the stations, tips shared, edges following the stations", () => {
    const s = spec(), fv = defaultFrontView(s), e = stationExtent(s.stations[1]);
    expect(fv.upper[0]).toEqual(fv.lower[0]);
    expect(fv.upper.at(-1)).toEqual(fv.lower.at(-1));
    expect(fv.upper[0][0]).toBeLessThan(-30);
    expect(fv.upper.at(-1)![0]).toBeGreaterThan(30);
    const mid = fv.upper.findIndex((q) => Math.abs(q[0]) < 1e-6);
    expect(fv.upper[mid][1]).toBeCloseTo(e.yHi, 0);
    expect(fv.lower[mid][1]).toBeCloseTo(e.yLo, 0);
  });

  it("the default top view runs from the wall to the wall", () => {
    const P = defaultTopView(spec()).points;
    expect(P[0][1]).toBe(0);
    expect(P.at(-1)![1]).toBe(0);
    expect(Math.max(...P.map((q) => q[1]))).toBeGreaterThan(10);
  });

  it("defaults exist for an empty hold too", () => {
    const s = fromSpec(EMPTY);
    expect(defaultFrontView(s).upper.length).toBe(5);
    expect(defaultTopView(s).points.length).toBe(5);
  });

  it("moving a tip moves both edges and stops short of the points between the tips", () => {
    const fv = defaultFrontView(spec());
    moveFrontPoint(fv, "lower", 0, [100, 33]);           // dragged far right, from the lower edge
    const inner = Math.min(...[...fv.upper.slice(1, -1), ...fv.lower.slice(1, -1)].map((q) => q[0]));
    expect(fv.upper[0]).toEqual(fv.lower[0]);
    expect(fv.upper[0][1]).toBe(33);
    expect(fv.upper[0][0]).toBeLessThanOrEqual(inner - TIP_GAP + 1e-9);
  });

  it("points between the tips stay between them", () => {
    const fv = defaultFrontView(spec());
    moveFrontPoint(fv, "upper", 2, [500, 70]);
    expect(fv.upper[2][0]).toBe(fv.upper.at(-1)![0] - TIP_GAP);
    expect(fv.upper[2][1]).toBe(70);
  });

  it("top view ends stay on the wall; other points stay in front of it", () => {
    const tv = defaultTopView(spec());
    moveTopPoint(tv, 0, [-90, 12]);
    expect(tv.points[0]).toEqual([-90, 0]);
    moveTopPoint(tv, 2, [0, -5]);
    expect(tv.points[2][1]).toBe(0);
  });

  it("inserting lands on the curve in the right span; the ends can't be removed", () => {
    const tv = defaultTopView(spec()), P = tv.points;
    tv.corners = [3];
    const r = nearestOnCurve(P, tv.corners, [P[1][0] + 2, P[1][1] + 0.5]);
    expect(r.dist).toBeLessThan(1);
    const k = insertCurvePoint(P, r.index, r.point, tv.corners);
    expect([1, 2]).toContain(k);
    expect(P.length).toBe(6);
    expect(tv.corners).toEqual([4]);                     // shifted with its point
    expect(removeCurvePoint(P, 0).ok).toBe(false);
    expect(removeCurvePoint(P, P.length - 1).ok).toBe(false);
    expect(removeCurvePoint(P, k, tv.corners).ok).toBe(true);
    expect(tv.corners).toEqual([3]);
  });

  it("front and top views round-trip through the file format", () => {
    const s = spec();
    s.front_view = defaultFrontView(s);
    s.top_view = defaultTopView(s);
    const again = fromSpec(toSpec(s));
    expect(again.front_view).toEqual(s.front_view);
    expect(again.top_view).toEqual(s.top_view);
  });
});
