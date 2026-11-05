import { describe, expect, it } from "vitest";
import type { Vec2 } from "../geometry/curves";
import {
  autoLandmarks, insertPoint, landmarkNames, landmarkOrder, movePoint, placeLandmarkEverywhere, removePoint, setLandmark,
  sortStations, toggleCorner,
} from "./edit";
import { fromSpec, toSpec, type EditableSpec, type EStation } from "./model";

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
