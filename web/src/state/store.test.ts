import { describe, expect, it } from "vitest";
import { Store, type Change } from "./store";

const base = () => ({
  schema: "hold-spec/1" as const,
  name: "t",
  stations: [
    { x: -20, points: [[0, 0], [10, 20], [0, 30]] as [number, number][], landmarks: {} },
    { x: 20, points: [[0, 0], [12, 22], [0, 31]] as [number, number][], landmarks: {} },
  ],
});
const tick = () => new Promise((r) => queueMicrotask(() => r(undefined)));

describe("Store", () => {
  it("undo and redo walk committed states", () => {
    const s = new Store(base());
    s.mutate((sp) => (sp.stations[0].x = -25));
    s.mutate((sp) => (sp.stations[0].x = -30));
    expect(s.spec.stations[0].x).toBe(-30);
    s.undo();
    expect(s.spec.stations[0].x).toBe(-25);
    s.undo();
    expect(s.spec.stations[0].x).toBe(-20);
    expect(s.canUndo).toBe(false);
    s.redo();
    expect(s.spec.stations[0].x).toBe(-25);
  });

  it("a drag (commit: false) becomes one undo step", () => {
    const s = new Store(base());
    for (const x of [-21, -22, -23]) s.mutate((sp) => (sp.stations[0].x = x), { commit: false });
    s.commit();
    s.undo();
    expect(s.spec.stations[0].x).toBe(-20);
  });

  it("a new edit clears the redo stack; no-op edits add no history", () => {
    const s = new Store(base());
    s.mutate((sp) => (sp.stations[0].x = -25));
    s.undo();
    s.mutate(() => {});
    expect(s.canRedo).toBe(true);
    s.mutate((sp) => (sp.stations[0].x = -26));
    expect(s.canRedo).toBe(false);
  });

  it("coalesces notifications into one batch per microtask", async () => {
    const s = new Store(base());
    const batches: Set<Change>[] = [];
    s.subscribe((c) => batches.push(c));
    s.mutate((sp) => (sp.stations[0].x = -21));
    s.select({ point: 1 });
    await tick();
    expect(batches.length).toBe(1);
    expect([...batches[0]].sort()).toEqual(["history", "selection", "spec"]);
  });

  it("clamps the selection when the selected point disappears", () => {
    const s = new Store(base());
    s.select({ station: 1, point: 2 });
    s.mutate((sp) => void sp.stations.splice(1, 1));
    expect(s.sel.station).toBe(0);
    expect(s.sel.point).toBe(2);
    s.mutate((sp) => void sp.stations[0].points.splice(1, 2));
    expect(s.sel.point).toBeNull();
  });
});
