// Section editor (z, y with the wall on the left): the authoritative drawing of each station.
import { evalOpen, type Vec2 } from "../geometry/curves";
import { autoLandmarks, insertPoint, isRoot, landmarkNames, landmarkOrder, movePoint, sortStations } from "../spec/edit";
import { tok } from "../theme";
import { Pane, type DragHandler } from "./pane";

export class SectionPane extends Pane {
  drawing: Vec2[] | null = null; // in-progress drawing (redraw of the selected station, or store.newStation)
  hung = false; // view tilted to the wall angle

  tool(): string {
    return this.app.store.tools.section;
  }

  setHung(on: boolean): void {
    this.hung = on;
    this.rot = on ? (-this.app.store.spec.wall_angle_deg * Math.PI) / 180 : 0;
    this.app.requestDraw();
  }

  /** Start drawing a new station at x (used when there is no section to copy, e.g. the first one). */
  startNew(x: number): void {
    this.drawing = null;
    this.app.store.setNewStation(x);
    this.app.store.setTool("section", "draw");
    this.fitView();
    this.app.requestDraw();
  }

  cancelDrawing(): void {
    this.drawing = null;
    if (this.app.store.newStation !== null) this.app.store.setNewStation(null);
  }

  private finishDrawing(pts: Vec2[]): void {
    const store = this.app.store;
    if (store.newStation !== null) {
      const x = store.newStation, names = landmarkNames(store.spec);
      store.setNewStation(null);
      store.mutate((s) => {
        // The first station gets lip_apex (its highest point); later ones follow the existing landmarks.
        const st = { x, points: pts, corners: [], note: "", landmarks: autoLandmarks(pts, s.stations.length ? names : ["lip_apex"]) };
        s.stations.push(st);
        store.sel.station = sortStations(s, st);
        store.sel.point = null;
      });
    } else {
      const names = Object.keys(store.station.landmarks);
      store.mutate((s) => {
        const t = s.stations[store.sel.station];
        t.points = pts;
        t.corners = [];
        t.landmarks = autoLandmarks(pts, names);
      });
    }
    store.setTool("section", "select");
  }

  protected onDown(w: Vec2): DragHandler | null {
    const store = this.app.store, st = store.station;
    if (store.tools.section === "draw" && (st || store.newStation !== null)) {
      if (!this.drawing) this.drawing = [[0, w[1]]];
      else if (w[0] < 1.5 && this.drawing.length >= 3) {
        const pts: Vec2[] = [...this.drawing, [0, w[1]]];
        this.drawing = null;
        this.finishDrawing(pts);
      } else this.drawing.push([Math.max(0, w[0]), w[1]]);
      this.app.requestDraw();
      return null;
    }
    if (!st || store.newStation !== null) return null;
    if (store.tools.section !== "select") return null;
    let hit: number | null = null;
    st.points.forEach((p, i) => {
      if (this.near(p, w)) hit = i;
    });
    store.select({ point: hit });
    if (hit === null) return null;
    const i: number = hit;
    return {
      move: (p) => store.mutate((s) => movePoint(s.stations[store.sel.station], i, p), { commit: false }),
      up: (moved) => {
        if (moved) store.mutate(() => {});
      },
    };
  }

  protected override onDblClick(w: Vec2): void {
    const store = this.app.store, st = store.station;
    if (!st || store.tools.section !== "select") return;
    const { dense, idx } = evalOpen(st.points, st.corners, 0.05);
    let bi = 0, bd = Infinity;
    dense.forEach((q, i) => {
      const d = Math.hypot(q[0] - w[0], q[1] - w[1]);
      if (d < bd) {
        bd = d;
        bi = i;
      }
    });
    if (bd * this.sc > 12) return;
    let k = 0;
    while (k < idx.length - 1 && idx[k + 1] <= bi) k++;
    store.mutate((s) => insertPoint(s.stations[store.sel.station], k + 1, dense[bi]));
    store.select({ point: k + 1 });
  }

  protected override onHover(): void {
    if (this.drawing) this.app.requestDraw();
  }

  fitView(): void {
    let y0 = Infinity, y1 = -Infinity, z1 = 5;
    for (const st of this.app.store.spec.stations)
      for (const [z, y] of st.points) {
        y0 = Math.min(y0, y); y1 = Math.max(y1, y); z1 = Math.max(z1, z);
      }
    if (!isFinite(y0)) [y0, y1, z1] = [0, 80, 40]; // nothing drawn yet: room for a typical hold
    this.fitTo(-4, z1 + 2, y0, y1, 0.06);
  }

  draw(): void {
    const store = this.app.store, st = store.station, c = this.ctx;
    this.clear();
    this.drawUnderlay();
    this.grid();
    const acc = tok("--accent"), acc2 = tok("--accent2"), ink = tok("--ink"), muted = tok("--muted");
    // the wall, in world coordinates so it tilts with the hung view
    this.path([[-6, -400], [0, -400], [0, 400], [-6, 400]], true);
    c.fillStyle = tok("--wall");
    c.fill();
    if (!st && store.newStation === null) {
      this.message("No stations yet. Pick + Station in the front or top view, then click where the first section goes.");
      return;
    }
    const order = store.spec.stations;
    // Ghost the neighbours: of the selected station, or of where the new one will go.
    let prev: typeof st | undefined, next: typeof st | undefined;
    if (store.newStation !== null) {
      const x = store.newStation;
      prev = [...order].reverse().find((s) => s.x < x);
      next = order.find((s) => s.x > x);
    } else {
      prev = order[store.sel.station - 1];
      next = order[store.sel.station + 1];
    }
    ([[prev, acc2, [5, 4]], [next, muted, [2, 4]]] as const).forEach(([s2, col, dash]) => {
      if (!s2) return;
      this.path(evalOpen(s2.points, s2.corners, 0.2).dense);
      c.setLineDash([...dash]);
      c.strokeStyle = col;
      c.lineWidth = 1.2;
      c.stroke();
      c.setLineDash([]);
      const top = s2.points.reduce((a, q) => (q[1] > a[1] ? q : a));
      this.text(top, `x ${Math.round(s2.x * 100) / 100}`, col, 6, -6);
    });
    if (this.drawing) {
      const h = this.hoverW;
      const pts: Vec2[] = h ? [...this.drawing, [Math.max(0, h[0]), h[1]]] : this.drawing;
      if (pts.length >= 2) {
        this.path(evalOpen(pts, [], 0.2).dense);
        c.strokeStyle = acc;
        c.lineWidth = 2;
        c.stroke();
      }
      this.drawing.forEach((q) => this.dot(q, 4, acc, null));
      return;
    }
    if (store.newStation !== null || !st) {
      this.message(`New station at x = ${store.newStation}: click on the wall where the face starts, then up the face and over the lip, then on the wall again to finish.`);
      return;
    }
    const { dense } = evalOpen(st.points, st.corners, 0.1);
    this.path([...dense, [0, dense[0][1]]], true);
    c.fillStyle = tok("--accent-soft");
    c.fill();
    this.path(dense);
    c.strokeStyle = ink;
    c.lineWidth = 2;
    c.stroke();
    const apexIdx = st.landmarks.lip_apex;
    if (apexIdx !== undefined) {
      this.path([st.points[st.points.length - 1], st.points[apexIdx]]);
      c.setLineDash([4, 4]);
      c.strokeStyle = muted;
      c.lineWidth = 1;
      c.stroke();
      c.setLineDash([]);
    }
    const byIndex = new Map(landmarkOrder(st).map(([k, v]) => [v, k]));
    st.points.forEach((q, j) => {
      const on = j === store.sel.point, corner = st.corners.includes(j), name = byIndex.get(j);
      this.dot(q, on ? 6 : name ? 5 : 4, on ? acc : name ? ink : tok("--panel"), on ? acc : ink, corner);
      if (name && !isRoot(st, j)) this.text(q, name, ink, 8, -6, `11px ${tok("--font-display")}`);
    });
  }
}
