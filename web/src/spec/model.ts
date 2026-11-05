// Editor-side view of hold-spec/1: the generated types with every optional field filled in,
// so editing code never has to null-check defaults. `toSpec` produces the file format again.
import type { BuildSettings, Dent, EndCaps, Groove, HoldSpec, Mounting, Note, Station, View } from "../api/types.gen";
import type { Vec2 } from "../geometry/curves";

export type Feature = Dent | Groove;
export interface EStation extends Required<Omit<Station, "points">> {
  points: Vec2[];
}
export interface EView extends Required<Omit<View, "points">> {
  points: Vec2[];
}
export interface EditableSpec {
  schema: "hold-spec/1";
  name: string;
  units: "mm";
  wall_angle_deg: number;
  description: string;
  stations: EStation[];
  front_view: EView | null;
  top_view: EView | null;
  end_caps: Required<EndCaps>;
  features: Feature[];
  mounting: Required<Mounting>;
  build: Required<BuildSettings>;
  notes: Note[];
}

export const ROOTS = ["bottom_root", "ledge_root"] as const;

const view = (v: View | null | undefined): EView | null =>
  v ? { points: v.points.map((p) => [p[0], p[1]] as Vec2), strength: v.strength ?? 0.5, corners: [...(v.corners ?? [])] } : null;

export function fromSpec(s: HoldSpec): EditableSpec {
  const stations = s.stations
    .map((t): EStation => ({
      x: t.x,
      points: t.points.map((p) => [p[0], p[1]] as Vec2),
      landmarks: Object.fromEntries(Object.entries(t.landmarks ?? {}).filter(([k]) => !(ROOTS as readonly string[]).includes(k))),
      corners: [...(t.corners ?? [])],
      note: t.note ?? "",
    }))
    .sort((a, b) => a.x - b.x);
  return {
    schema: "hold-spec/1",
    name: s.name,
    units: "mm",
    wall_angle_deg: s.wall_angle_deg ?? 45,
    description: s.description ?? "",
    stations,
    front_view: view(s.front_view),
    top_view: view(s.top_view),
    end_caps: { radius: s.end_caps?.radius ?? 6 },
    features: structuredClone(s.features ?? []),
    mounting: {
      screws: (s.mounting?.screws ?? []).map((p) => [p[0], p[1]] as Vec2),
      hole_dia: s.mounting?.hole_dia ?? 4.8,
      countersink_dia: s.mounting?.countersink_dia ?? 10,
    },
    build: { voxel: 0.3, smooth_sigma_vox: 0.5, sample_step: 0.2, ...(s.build ?? {}) },
    notes: structuredClone(s.notes ?? []),
  };
}

const r2 = (v: number) => Math.round(v * 100) / 100;
const rp = (pts: number[][]) => pts.map((p) => p.map(r2));

/** The file format, coordinates rounded to 0.01 mm (well under print and sanding tolerance). */
export function toSpec(e: EditableSpec): HoldSpec {
  return {
    schema: "hold-spec/1",
    name: e.name,
    units: "mm",
    wall_angle_deg: e.wall_angle_deg,
    description: e.description,
    stations: e.stations.map((t) => ({ x: r2(t.x), points: rp(t.points) as Vec2[], landmarks: { ...t.landmarks }, corners: [...t.corners], note: t.note })),
    front_view: e.front_view && { ...e.front_view, points: rp(e.front_view.points) as Vec2[] },
    top_view: e.top_view && { ...e.top_view, points: rp(e.top_view.points) as Vec2[] },
    end_caps: { ...e.end_caps },
    features: e.features.map((f) => (f.type === "dent" ? { ...f, center: f.center.map(r2) } : { ...f, path: rp(f.path) })),
    mounting: { ...e.mounting, screws: rp(e.mounting.screws) as Vec2[] },
    build: { ...e.build },
    notes: e.notes.map((n) => ({ ...n, anchor: { ...n.anchor, at: n.anchor.at.map(r2) as Vec2 } })),
  };
}

export function slug(s: string): string {
  const v = (s || "hold").toLowerCase().replace(/[^a-z0-9_.-]+/g, "_").replace(/^[_.-]+|_+$/g, "").slice(0, 80);
  return v || "hold";
}

export const BLANK: HoldSpec = {
  schema: "hold-spec/1",
  name: "new_hold",
  wall_angle_deg: 45,
  stations: [
    { x: -30, points: [[0, 10], [7, 20], [12, 32], [13.5, 40], [11, 45], [6, 43.5], [0, 42]], landmarks: { lip_apex: 4 } },
    { x: 30, points: [[0, 10], [7, 20], [12, 32], [13.5, 40], [11, 45], [6, 43.5], [0, 42]], landmarks: { lip_apex: 4 } },
  ],
};
