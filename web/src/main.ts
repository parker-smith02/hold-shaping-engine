// Holdgen Studio entry point: builds the store, panes and panels and wires them together.
import "./styles.css";
import { ApiError, api } from "./api/client";
import type { HoldSpec } from "./api/types.gen";
import { $ } from "./dom";
import { FrontPane } from "./panes/front";
import type { Ctx } from "./panes/pane";
import { SectionPane } from "./panes/section";
import { TopPane } from "./panes/top";
import { removePoint, sortStations, toggleCorner } from "./spec/edit";
import { BLANK, slug } from "./spec/model";
import { PreviewSync } from "./state/preview";
import { Store, type PaneName } from "./state/store";
import { onThemeChange } from "./theme";
import { BuildPanel } from "./ui/build";
import { setupDialog } from "./ui/dialog";
import { Library } from "./ui/library";
import * as panels from "./ui/panels";
import { View3D } from "./view3d";

const DRAFT_KEY = "holdgen.draft.v1";

function toast(msg: string, ms = 2800): void {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout((toast as unknown as { t?: number }).t);
  (toast as unknown as { t?: number }).t = window.setTimeout(() => (t.hidden = true), ms);
}

function readDraft(): HoldSpec | null {
  try {
    const v = localStorage.getItem(DRAFT_KEY);
    const s = v ? (JSON.parse(v) as HoldSpec) : null;
    return s && Array.isArray(s.stations) ? s : null;
  } catch {
    return null;
  }
}

async function initialSpec(): Promise<HoldSpec> {
  const want = new URLSearchParams(location.search).get("hold");
  if (want) {
    try {
      return await api.getHold(want);
    } catch {
      toast(`holds/${want}.json not found; opened your last draft instead.`);
    }
  }
  const draft = readDraft();
  if (draft) return draft;
  try {
    return await api.getHold("ravage_example");
  } catch {
    return structuredClone(BLANK);
  }
}

async function main(): Promise<void> {
  const store = new Store(await initialSpec());
  const preview = new PreviewSync(() => store.toSpec());

  let drawQueued = false;
  const requestDraw = () => {
    if (drawQueued) return;
    drawQueued = true;
    requestAnimationFrame(() => {
      drawQueued = false;
      front.draw();
      top.draw();
      section.draw();
    });
  };

  const addStationAt = async (x: number) => {
    const spec = store.spec;
    if (spec.stations.some((s) => Math.abs(s.x - x) < 1)) return toast("A station already sits within 1 mm of that spot.");
    const loft = preview.state.data?.loft;
    let st;
    if (loft && x >= loft.x_min && x <= loft.x_max && !preview.state.stale) {
      try {
        const s = await api.sectionAt(store.toSpec(), x);
        st = { x: s.x, points: s.points, landmarks: s.landmarks ?? {}, corners: [], note: "" };
      } catch (e) {
        toast(e instanceof ApiError ? e.body.error : (e as Error).message);
        return;
      }
    } else {
      const near = spec.stations.reduce((a, s) => (Math.abs(s.x - x) < Math.abs(a.x - x) ? s : a));
      st = { ...structuredClone(near), x, note: "" };
    }
    store.mutate((s) => {
      s.stations.push(st);
      store.sel.station = sortStations(s, st);
      store.sel.point = null;
    });
    store.setTool("front", "select");
    store.setTool("top", "select");
    toast(`Added a station at x = ${x}, shaped from the current loft.`);
  };

  const ctx: Ctx = { store, preview, toast, addStationAt, requestDraw };
  const front = new FrontPane($<HTMLCanvasElement>("#cvFront"), ctx);
  const top = new TopPane($<HTMLCanvasElement>("#cvTop"), ctx);
  const section = new SectionPane($<HTMLCanvasElement>("#cvSection"), ctx);
  const panes: Record<PaneName, FrontPane | TopPane | SectionPane> = { front, top, section };
  const view3d = new View3D($<HTMLCanvasElement>("#cv3d"));
  const library = new Library(store, toast);
  new BuildPanel(store, toast);
  const dialog = setupDialog(store, toast);
  const pctx: panels.PanelCtx = {
    store,
    toast,
    beginAddStation: () => {
      store.setTool("front", "station");
      store.setTool("top", "station");
      toast("Click the front or top view where the new station goes.");
    },
  };

  // ------------------------------------------------------------------ toolbars
  type Btn = [id: string, label: string, title?: string];
  const pickImage = (pane: PaneName) => {
    const inp = document.createElement("input");
    inp.type = "file";
    inp.accept = "image/*";
    inp.onchange = () => {
      const f = inp.files?.[0];
      if (!f) return;
      panes[pane].loadUnderlay(f);
      store.setTool(pane, "image");
      toast("Reference image loaded. Drag to place it, wheel to scale it, then pick another tool.");
    };
    inp.click();
  };
  const actions: Record<string, (pane: PaneName) => void> = {
    image: pickImage,
    fit: (pane) => panes[pane].fitView(),
    hang: () => {
      section.setHung(!section.hung);
      refreshToolbars();
    },
  };
  const toolbars: Record<PaneName, Btn[]> = {
    front: [["select", "Select"], ["outline", "Outline"], ["station", "+ Station"], ["screw", "Screw"], ["dent", "Dent"], ["groove", "Groove"], ["note", "Note"], ["!image", "Image…", "Trace over a reference photo"], ["!fit", "Fit"]],
    top: [["select", "Select"], ["outline", "Outline"], ["station", "+ Station"], ["dent", "Ledge dent"], ["groove", "Ledge groove"], ["!image", "Image…", "Trace over a reference photo"], ["!fit", "Fit"]],
    section: [["select", "Select"], ["draw", "Redraw", "Clear this station and draw it again"], ["!hang", "Hang", "Tilt the section to the wall angle"], ["!image", "Image…", "Trace over a reference photo"], ["!fit", "Fit"]],
  };
  const hints: Record<string, string> = {
    select: "drag points · double-click a curve to add a point · drag empty space to pan · wheel to zoom",
    outline: "click to add outline points; each slots into the nearest segment",
    station: "click to add a station there, shaped from the current loft",
    screw: "click to place a screw", dent: "click to place a dent", groove: "click points; double-click or Enter to finish", note: "click to pin a note",
    image: "drag to move the reference image · wheel to scale it",
    draw: "click from the bottom root up the face, over the lip, then click at the wall to finish",
  };
  for (const pane of ["front", "top", "section"] as PaneName[]) {
    const el = $(`#tools${pane[0].toUpperCase()}${pane.slice(1)}`);
    for (const [id, label, title] of toolbars[pane]) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.title = title ?? label;
      b.dataset.tool = id;
      b.addEventListener("click", () => {
        if (id.startsWith("!")) return actions[id.slice(1)](pane);
        const cur = store.tools[pane];
        store.setTool(pane, (cur === id ? "select" : id) as never);
        front.pendingGroove = top.pendingGroove = null;
        section.drawing = null;
      });
      el.append(b);
    }
  }
  function refreshToolbars(): void {
    for (const pane of ["front", "top", "section"] as PaneName[]) {
      document.querySelectorAll<HTMLButtonElement>(`#tools${pane[0].toUpperCase()}${pane.slice(1)} button`).forEach((b) => {
        b.classList.toggle("on", b.dataset.tool === store.tools[pane] || (b.dataset.tool === "!hang" && section.hung));
      });
      $(`#hint${pane[0].toUpperCase()}${pane.slice(1)}`).textContent = hints[store.tools[pane]] ?? "";
    }
  }

  // ------------------------------------------------------------------ state -> view
  let draftTimer: number | undefined;
  store.subscribe((changes) => {
    if (changes.has("spec")) {
      preview.request();
      clearTimeout(draftTimer);
      draftTimer = window.setTimeout(() => {
        try {
          localStorage.setItem(DRAFT_KEY, JSON.stringify(store.toSpec()));
        } catch {
          /* storage full or disabled: drafts are a convenience */
        }
      }, 300);
      panels.syncSettings(store);
    }
    if (changes.has("spec") || changes.has("selection")) {
      panels.renderStations(pctx);
      panels.renderPointRow(pctx);
      panels.renderInspector(pctx);
      panels.renderReadouts(pctx, preview.state);
    }
    if (changes.has("tools")) refreshToolbars();
    if (changes.has("load")) {
      fitAll();
      preview.request(true);
    }
    $<HTMLButtonElement>("#btnUndo").disabled = !store.canUndo;
    $<HTMLButtonElement>("#btnRedo").disabled = !store.canRedo;
    requestDraw();
  });

  let fittedOnce = false;
  preview.subscribe((s) => {
    view3d.update(s, store.spec.mounting);
    panels.renderReadouts(pctx, s);
    panels.renderIssues(s);
    const status = $("#serverStatus");
    status.textContent = s.error && !s.data ? "server unreachable" : s.latencyMs !== null ? `preview ${s.latencyMs} ms` : "";
    status.classList.toggle("bad", !!s.error && !s.data);
    if (s.data) {
      const [a, b] = [s.data.bbox.min, s.data.bbox.max];
      $("#sizeLabel").textContent = `${(b[0] - a[0]).toFixed(0)} × ${(b[1] - a[1]).toFixed(0)} × ${(b[2] - a[2]).toFixed(0)} mm${s.stale ? " · out of date" : ""}`;
      if (!fittedOnce) {
        fittedOnce = true;
        fitAll();
      }
    }
    requestDraw();
  });

  function fitAll(): void {
    requestAnimationFrame(() => {
      front.fitView();
      top.fitView();
      section.fitView();
      view3d.fit();
    });
  }

  // ------------------------------------------------------------------ header + settings
  $("#btnUndo").addEventListener("click", () => store.undo());
  $("#btnRedo").addEventListener("click", () => store.redo());
  $("#btnSave").addEventListener("click", () => void library.save());
  $("#btnImport").addEventListener("click", () => dialog.open("import"));
  $("#btnExport").addEventListener("click", () => dialog.open("export"));
  $("#btnNew").addEventListener("click", async () => {
    const b = $<HTMLButtonElement>("#btnNew");
    if (!b.dataset.armed) {
      b.dataset.armed = "1";
      b.textContent = "New: click again for a blank hold";
      setTimeout(() => {
        delete b.dataset.armed;
        b.textContent = "New";
      }, 3000);
      return;
    }
    delete b.dataset.armed;
    b.textContent = "New";
    store.load(structuredClone(BLANK));
  });
  $<HTMLInputElement>("#holdName").addEventListener("change", (e) => {
    const el = e.target as HTMLInputElement;
    store.mutate((s) => (s.name = slug(el.value)));
    el.value = store.spec.name;
  });
  $<HTMLInputElement>("#wallAngle").addEventListener("change", (e) => {
    const v = Math.max(0, Math.min(90, parseFloat((e.target as HTMLInputElement).value) || 0));
    store.mutate((s) => (s.wall_angle_deg = v));
    if (section.hung) section.setHung(true);
    if (view3d.hung) view3d.setHung(true, v);
  });
  $<HTMLTextAreaElement>("#desc").addEventListener("change", (e) => store.mutate((s) => (s.description = (e.target as HTMLTextAreaElement).value)));
  for (const [key, id] of [["front_view", "front"], ["top_view", "top"]] as const) {
    const r = $<HTMLInputElement>(`#${id}Strength`);
    r.addEventListener("input", () => store.mutate((s) => { if (s[key]) s[key]!.strength = parseFloat(r.value); }, { commit: false }));
    r.addEventListener("change", () => store.commit());
  }
  $("#btnHang").addEventListener("click", () => {
    view3d.setHung(!view3d.hung, store.spec.wall_angle_deg);
    $("#btnHang").classList.toggle("on", view3d.hung);
  });
  $("#btnFit3d").addEventListener("click", () => view3d.fit());
  onThemeChange(() => {
    view3d.applyTheme();
    requestDraw();
  });

  // ------------------------------------------------------------------ keyboard
  document.addEventListener("keydown", (e) => {
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    const mod = e.ctrlKey || e.metaKey, k = e.key.toLowerCase();
    if (mod && k === "z") {
      e.preventDefault();
      if (e.shiftKey) store.redo();
      else store.undo();
      return;
    }
    if (mod && k === "y") {
      e.preventDefault();
      store.redo();
      return;
    }
    if (mod && k === "s") {
      e.preventDefault();
      void library.save();
      return;
    }
    if (e.key === "Escape") {
      if (front.pendingGroove) front.finishGroove();
      if (top.pendingGroove) top.finishGroove();
      section.drawing = null;
      (["front", "top", "section"] as PaneName[]).forEach((p) => store.setTool(p, "select"));
      return;
    }
    if (e.key === "Enter") {
      if (front.pendingGroove) front.finishGroove();
      if (top.pendingGroove) top.finishGroove();
      return;
    }
    const active = document.activeElement;
    if ((e.key === "Delete" || e.key === "Backspace") && active === section.cv && store.sel.point !== null) {
      e.preventDefault();
      const res = removePoint(store.station, store.sel.point);
      if (!res.ok) return toast(res.reason);
      store.select({ point: null });
      store.mutate(() => {});
      return;
    }
    if ((e.key === "Delete" || e.key === "Backspace") && (active === front.cv || active === top.cv)) {
      const s = active === front.cv ? store.sel.front : store.sel.top;
      if (!s || s.kind === "station") return;
      e.preventDefault();
      store.mutate((spec) => {
        const v = active === front.cv ? spec.front_view : spec.top_view;
        if (s.kind === "outline" && v && v.points.length > 3) v.points.splice(s.i, 1);
        else if (s.kind === "screw") spec.mounting.screws.splice(s.i, 1);
        else if (s.kind === "dent" || s.kind === "groove") spec.features.splice(s.i, 1);
        else if (s.kind === "note") spec.notes.splice(s.i, 1);
      });
      store.select({ front: null, top: null });
      return;
    }
    if (k === "c" && active === section.cv && store.sel.point !== null) store.mutate((s) => toggleCorner(s.stations[store.sel.station], store.sel.point!));
  });

  // ------------------------------------------------------------------ boot
  refreshToolbars();
  panels.syncSettings(store);
  store.emit("spec", "selection", "load");
  void library.refresh();
  (window as unknown as { holdgen: unknown }).holdgen = { store, preview, panes, view3d }; // for debugging and e2e tests
}

void main();
