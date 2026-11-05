// Side panels: station chips, point editor, readouts, inspector, issues, hold settings.
import type { Issue, ReadoutRow, Readouts } from "../api/types.gen";
import { $, armed, h } from "../dom";
import {
  isRoot, landmarkNames, placeLandmarkEverywhere, removePoint, setLandmark, sortStations, toggleCorner,
} from "../spec/edit";
import { slug } from "../spec/model";
import type { PreviewState } from "../state/preview";
import type { Store } from "../state/store";

const r2 = (v: number) => Math.round(v * 100) / 100;
const fmt = (v: number | null | undefined, unit = "") => (v === null || v === undefined || !isFinite(v) ? "–" : `${v.toFixed(1)}${unit}`);

export interface PanelCtx {
  store: Store;
  toast(msg: string): void;
  beginAddStation(): void;
}

export function renderStations(ctx: PanelCtx): void {
  const { store } = ctx, el = $("#stationChips");
  el.replaceChildren(
    ...store.spec.stations.map((st, i) =>
      h("button", {
        type: "button", class: `chip${i === store.sel.station ? " sel" : ""}`, text: String(r2(st.x)), title: st.note,
        on: { click: () => store.select({ station: i, point: null }) },
      }),
    ),
    h("button", { type: "button", class: "chip add", text: "+ Station", title: "Pick a spot in the front or top view", on: { click: () => ctx.beginAddStation() } }),
  );
}

export function renderPointRow(ctx: PanelCtx): void {
  const { store } = ctx, el = $("#pointRow"), st = store.station;
  el.replaceChildren();
  if (!st) return;
  const x = h("input", { type: "number", id: "stX", step: 0.5, value: String(r2(st.x)) });
  x.addEventListener("change", () => {
    const v = parseFloat(x.value);
    if (!isFinite(v)) return;
    store.mutate((s) => {
      s.stations[store.sel.station].x = v;
      store.sel.station = sortStations(s, s.stations[store.sel.station]);
    });
  });
  const note = h("input", { type: "text", id: "stNote", placeholder: "note for this station", value: st.note });
  note.style.flex = "1 1 160px";
  note.addEventListener("change", () => store.mutate((s) => (s.stations[store.sel.station].note = note.value)));
  const del = h("button", { type: "button", class: "danger", text: "Delete station", disabled: store.spec.stations.length <= 2 });
  armed(del, "Delete station", () => store.mutate((s) => void s.stations.splice(store.sel.station, 1)));
  el.append(h("span", { class: "lbl", text: "Station x" }), x, note, del);

  const i = store.sel.point;
  if (i === null || !st.points[i]) return;
  const root = isRoot(st, i), q = st.points[i];
  const row = h("div", { class: "row" });
  row.style.width = "100%";
  const zi = h("input", { type: "number", id: "ptZ", step: 0.1, value: String(r2(q[0])), title: "out from the wall (mm)", disabled: root });
  const yi = h("input", { type: "number", id: "ptY", step: 0.1, value: String(r2(q[1])), title: "up the wall (mm)" });
  const apply = () => store.mutate((s) => {
    s.stations[store.sel.station].points[i] = [root ? 0 : Math.max(0, parseFloat(zi.value) || 0), parseFloat(yi.value) || 0];
  });
  zi.addEventListener("change", apply);
  yi.addEventListener("change", apply);
  const corner = h("button", { type: "button", text: st.corners.includes(i) ? "Corner ✓" : "Corner", disabled: root, on: { click: () => store.mutate((s) => toggleCorner(s.stations[store.sel.station], i)) } });
  const current = Object.entries(st.landmarks).find(([, v]) => v === i)?.[0] ?? "";
  const lm = h("select", { id: "ptLm", title: "Landmark", disabled: root },
    h("option", { value: "", text: root ? (i === 0 ? "bottom_root" : "ledge_root") : "no landmark" }),
    ...landmarkNames(store.spec).map((n) => h("option", { value: n, text: n })),
    h("option", { value: "__new", text: "New landmark…" }));
  lm.value = current;
  lm.addEventListener("change", () => {
    if (lm.value === "__new") {
      const name = h("input", { type: "text", id: "lmName", placeholder: "e.g. lip_start" });
      const ok = h("button", { type: "button", text: "Add to all stations" });
      ok.addEventListener("click", () => {
        const nm = slug(name.value);
        if (nm === "bottom_root" || nm === "ledge_root") return ctx.toast("bottom_root and ledge_root are implicit; pick another name.");
        store.mutate((s) => {
          const src = s.stations[store.sel.station];
          setLandmark(src, i, nm);
          placeLandmarkEverywhere(s, nm, src, i);
        });
      });
      row.append(name, ok);
      name.focus();
      return;
    }
    store.mutate((s) => setLandmark(s.stations[store.sel.station], i, lm.value || null));
  });
  const rm = h("button", { type: "button", class: "danger", text: "Remove point", disabled: root });
  rm.addEventListener("click", () => {
    const res = removePoint(store.station, i);
    if (!res.ok) return ctx.toast(res.reason);
    store.select({ point: null });
    store.mutate(() => {});
  });
  row.append(h("span", { class: "lbl", text: `Point ${i}` }), h("span", { class: "muted mono", text: "z" }), zi, h("span", { class: "muted mono", text: "y" }), yi, corner, lm, rm);
  el.append(row);
}

function readoutFor(rows: ReadoutRow[] | undefined, x: number): Readouts | null {
  return rows?.find((r) => r.kind === "station" && Math.abs(r.x - x) < 1e-6)?.readouts ?? null;
}

export function renderReadouts(ctx: PanelCtx, preview: PreviewState): void {
  const { store } = ctx, st = store.station, el = $("#readouts");
  const r = st ? readoutFor(preview.data?.readouts, st.x) : null;
  const wall = store.spec.wall_angle_deg;
  const items: [string, string][] = [
    ["Edge depth", fmt(r?.depth, " mm")], ["Chord incut", fmt(r?.chord_incut, "°")], ["Incut at wall", fmt(r?.incut_at_wall, "°")],
    ["Incut near lip", fmt(r?.incut_near_lip, "°")], [`Ledge on ${wall}° wall`, fmt(r?.ledge_below_horizontal_on_wall, "° down")], ["Thickness", fmt(r?.thickness, " mm")],
  ];
  el.replaceChildren(...items.map(([k, v]) => h("div", { class: "ro" }, h("div", { class: "k", text: k }), h("div", { class: "v", text: v }))));
  const t = $("#roTable");
  const head = h("tr", {}, ...["x", "", "depth", "chord", "at wall", "near lip", "on wall", "thick"].map((s) => h("th", { text: s })));
  const rows = (preview.data?.readouts ?? []).map((row) =>
    h("tr", { class: row.kind }, ...[
      String(r2(row.x)), row.kind === "station" ? "●" : "·", fmt(row.readouts.depth), fmt(row.readouts.chord_incut, "°"),
      fmt(row.readouts.incut_at_wall, "°"), fmt(row.readouts.incut_near_lip, "°"), fmt(row.readouts.ledge_below_horizontal_on_wall, "°"), fmt(row.readouts.thickness),
    ].map((s) => h("td", { text: s }))));
  t.replaceChildren(head, ...rows);
  $("#secTitle").textContent = st ? `x = ${r2(st.x)} mm` : "";
}

export function renderIssues(preview: PreviewState): void {
  const el = $("#issues");
  const list: Issue[] = preview.issues;
  const items: HTMLElement[] = [];
  if (preview.error && !list.length) items.push(h("div", { class: "issue", text: preview.error }));
  for (const i of list) items.push(h("div", { class: `issue ${i.level}`, text: i.message }));
  if (!items.length && preview.data) items.push(h("div", { class: "issue ok", text: "Spec is valid and ready to build." }));
  el.replaceChildren(...items);
}

export function renderInspector(ctx: PanelCtx): void {
  const { store } = ctx, el = $("#inspector"), s = store.sel.front ?? store.sel.top, which = store.sel.front ? "front" : "top";
  const num = (label: string, id: string, val: number, step: number, set: (v: number) => void) => {
    const i = h("input", { type: "number", id, step, value: String(r2(val)) });
    i.addEventListener("change", () => {
      const v = parseFloat(i.value);
      if (isFinite(v)) store.mutate(() => set(v));
    });
    return h("span", { class: "row" }, h("label", { htmlFor: id, text: label }), i);
  };
  const remove = (label: string, fn: () => void) => {
    const b = h("button", { type: "button", class: "danger", text: label });
    b.addEventListener("click", () => {
      store.select({ front: null, top: null });
      store.mutate(fn);
    });
    return b;
  };
  if (!s) {
    el.replaceChildren(h("h4", { text: "Nothing selected" }), h("p", { class: "help", text: "Select an outline point, station line, screw, feature or note in the front or top view to edit it here." }));
    return;
  }
  const spec = store.spec;
  if (s.kind === "outline") {
    const v = which === "front" ? spec.front_view : spec.top_view;
    if (!v) return;
    el.replaceChildren(
      h("h4", { text: `${which === "front" ? "Front" : "Top"} view, point ${s.i}` }),
      h("div", { class: "row" },
        remove("Remove point", () => {
          if (v.points.length > 3) v.points.splice(s.i, 1);
          else ctx.toast("An outline needs at least three points; clear the view instead.");
        }),
        h("button", { type: "button", text: v.corners.includes(s.i) ? "Corner ✓" : "Corner", on: { click: () => store.mutate(() => { v.corners = v.corners.includes(s.i) ? v.corners.filter((c) => c !== s.i) : [...v.corners, s.i]; }) } }),
        remove("Clear this view", () => { if (which === "front") spec.front_view = null; else spec.top_view = null; })));
  } else if (s.kind === "station") {
    el.replaceChildren(h("h4", { text: `Station x = ${r2(spec.stations[s.i]?.x ?? 0)}` }), h("p", { class: "help", text: "Drag the line to move it. Edit its shape in the section editor." }));
  } else if (s.kind === "screw") {
    const q = spec.mounting.screws[s.i];
    if (!q) return;
    el.replaceChildren(
      h("h4", { text: `Screw ${s.i + 1}` }),
      h("div", { class: "row" }, num("x", "scX", q[0], 0.5, (v) => (q[0] = v)), num("y", "scY", q[1], 0.5, (v) => (q[1] = v)), remove("Remove", () => spec.mounting.screws.splice(s.i, 1))),
      h("div", { class: "row" }, num("Hole Ø", "hole", spec.mounting.hole_dia, 0.1, (v) => (spec.mounting.hole_dia = v)), num("Countersink Ø", "csink", spec.mounting.countersink_dia, 0.5, (v) => (spec.mounting.countersink_dia = v))));
  } else if (s.kind === "dent" || s.kind === "groove") {
    const f = spec.features[s.i];
    if (!f) return;
    const dims = f.type === "dent"
      ? [num("Size x", "fSx", (f.size ?? [8, 8, 4])[0], 0.5, (v) => (f.size = [v, (f.size ?? [8, 8, 4])[1], (f.size ?? [8, 8, 4])[2]])),
         num("y", "fSy", (f.size ?? [8, 8, 4])[1], 0.5, (v) => (f.size = [(f.size ?? [8, 8, 4])[0], v, (f.size ?? [8, 8, 4])[2]])),
         num("z", "fSz", (f.size ?? [8, 8, 4])[2], 0.5, (v) => (f.size = [(f.size ?? [8, 8, 4])[0], (f.size ?? [8, 8, 4])[1], v]))]
      : [num("Width", "fW", f.width ?? 6, 0.5, (v) => (f.width = v))];
    const note = h("input", { type: "text", id: "fNote", value: f.note ?? "", placeholder: "what this feature is for" });
    note.style.width = "100%";
    note.addEventListener("change", () => store.mutate(() => (f.note = note.value)));
    el.replaceChildren(
      h("h4", { text: `${f.type === "dent" ? "Dent" : "Groove"} on the ${f.surface === "front" ? "face" : "ledge"}` }),
      h("div", { class: "row" }, num("Depth", "fDepth", f.depth, 0.1, (v) => (f.depth = v)), ...dims),
      h("p", { class: "help", text: "Positive depth removes material, negative adds it. Sizes are 1-sigma radii in mm." }),
      note, remove("Remove feature", () => spec.features.splice(s.i, 1)));
  } else if (s.kind === "note") {
    const n = spec.notes[s.i];
    if (!n) return;
    const t = h("textarea", { id: "noteText", value: n.text ?? "", placeholder: "Tell Claude what you want at this spot." });
    t.addEventListener("change", () => store.mutate(() => (n.text = t.value)));
    el.replaceChildren(h("h4", { text: "Pinned note" }), t, remove("Remove note", () => spec.notes.splice(s.i, 1)));
  }
}

export function syncSettings(store: Store): void {
  const s = store.spec;
  const name = $<HTMLInputElement>("#holdName");
  if (document.activeElement !== name) name.value = s.name;
  $<HTMLInputElement>("#wallAngle").value = String(s.wall_angle_deg);
  const desc = $<HTMLTextAreaElement>("#desc");
  if (document.activeElement !== desc) desc.value = s.description;
  for (const [key, id] of [["front_view", "front"], ["top_view", "top"]] as const) {
    const v = s[key], r = $<HTMLInputElement>(`#${id}Strength`);
    r.disabled = !v;
    r.value = String(v ? v.strength : 0.5);
    $(`#${id}StrengthV`).textContent = v ? v.strength.toFixed(2) : "off";
  }
}
