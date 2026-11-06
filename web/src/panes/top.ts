// Top view (x, z looking down, wall at the bottom): loose plan outline, stations, ledge features.
import { evalOpen, type Vec2 } from "../geometry/curves";
import { insertCurvePoint, moveTopPoint, nearestOnCurve, sortStations, stationExtent } from "../spec/edit";
import type { Hit } from "../state/store";
import { tok } from "../theme";
import { drawFeatures, hitFeature } from "./features";
import { Pane, type DragHandler } from "./pane";

const snapX = (x: number) => Math.round(x * 2) / 2;

export class TopPane extends Pane {
  pendingGroove: Vec2[] | null = null;

  tool(): string {
    return this.app.store.tools.top;
  }

  private hit(w: Vec2): Hit | null {
    const { spec } = this.app.store;
    const P = spec.top_view?.points ?? [];
    for (const i of [0, P.length - 1, ...P.keys()]) if (P[i] && this.near(P[i], w, i === 0 || i === P.length - 1 ? 11 : 9)) return { kind: "outline", i };
    const f = hitFeature(this, spec.features, "ledge", w);
    if (f) return f;
    for (let i = 0; i < spec.stations.length; i++) {
      const e = stationExtent(spec.stations[i]), x = spec.stations[i].x;
      if (Math.abs((x - w[0]) * this.sc) < 7 && w[1] > -2 && w[1] < e.zHi + 3) return { kind: "station", i };
    }
    return null;
  }

  protected onDown(w: Vec2): DragHandler | null {
    const store = this.app.store, t = store.tools.top;
    const z = Math.max(0, w[1]);
    if (t === "select") {
      const h = this.hit(w);
      store.select(h?.kind === "station" ? { top: h, station: h.i, point: null } : { top: h });
      if (!h) return null;
      const tracked = h.kind === "station" ? store.spec.stations[h.i] : null;
      return {
        move: (p) => store.mutate((s) => {
          const pz = Math.max(0, p[1]);
          if (h.kind === "outline") moveTopPoint(s.top_view!, h.i, p);
          else if (h.kind === "station") s.stations[h.i].x = snapX(p[0]);
          else if (h.kind === "dent") (s.features[h.i] as { center: number[] }).center = [p[0], pz];
          else if (h.kind === "groove") (s.features[h.i] as { path: number[][] }).path[h.j] = [p[0], pz];
        }, { commit: false }),
        up: (moved) => {
          if (!moved) return;
          if (tracked) store.select({ station: sortStations(store.spec, tracked) });
          store.mutate(() => {});
        },
      };
    }
    if (t === "station") {
      void this.app.addStationAt(snapX(w[0]));
      return null;
    }
    if (t === "dent") {
      store.mutate((s) => s.features.push({ type: "dent", surface: "ledge", center: [w[0], z], size: [9, 3, 4], depth: 1.5, note: "" }));
      store.select({ top: { kind: "dent", i: store.spec.features.length - 1 } });
      store.setTool("top", "select");
      return null;
    }
    if (t === "groove") {
      (this.pendingGroove ??= []).push([w[0], z]);
      this.app.requestDraw();
      return null;
    }
    return null;
  }

  protected override onDblClick(w: Vec2): void {
    const store = this.app.store;
    if (store.tools.top === "groove" && this.pendingGroove) {
      this.finishGroove();
      return;
    }
    const tv = store.spec.top_view;
    if (store.tools.top !== "select" || !tv) return;
    const r = nearestOnCurve(tv.points, tv.corners, w);
    if (r.dist * this.sc > 10) return;
    let at = r.index;
    store.mutate((s) => (at = insertCurvePoint(s.top_view!.points, r.index, r.point, s.top_view!.corners)));
    store.select({ top: { kind: "outline", i: at } });
  }

  finishGroove(): void {
    const store = this.app.store, path = this.pendingGroove;
    this.pendingGroove = null;
    if (path && path.length >= 2) {
      store.mutate((s) => s.features.push({ type: "groove", surface: "ledge", path, width: 3, depth: 0.5, note: "" }));
      store.select({ top: { kind: "groove", i: store.spec.features.length - 1, j: 0 } });
    }
    store.setTool("top", "select");
  }

  fitView(): void {
    const { spec } = this.app.store;
    let x0 = Infinity, x1 = -Infinity, z1 = 5;
    for (const st of spec.stations) {
      x0 = Math.min(x0, st.x);
      x1 = Math.max(x1, st.x);
      z1 = Math.max(z1, stationExtent(st).zHi);
    }
    spec.top_view?.points.forEach((p) => {
      x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); z1 = Math.max(z1, p[1]);
    });
    const d = this.app.preview.state.data;
    if (d && spec.stations.length) {
      x0 = Math.min(x0, d.loft.x_min);
      x1 = Math.max(x1, d.loft.x_max);
    }
    if (!isFinite(x0)) [x0, x1] = [-60, 60]; // nothing drawn yet
    this.fitTo(x0, x1, -2, z1, 0.1);
  }

  draw(): void {
    const { spec, sel } = this.app.store, c = this.ctx;
    this.clear();
    this.drawUnderlay();
    this.grid();
    const acc = tok("--accent"), ink = tok("--ink"), muted = tok("--muted");
    const [, wallY] = this.toScreen(0, 0);
    c.fillStyle = tok("--wall");
    c.fillRect(0, wallY, this.W, Math.max(4, 3 * this.sc));
    const d = this.app.preview.state.data;
    if (d && spec.stations.length) {
      const { x, z_hi } = d.extents;
      if (x.length) {
        this.path([[x[0], 0], ...x.map((v, i) => [v, z_hi[i]]), [x[x.length - 1], 0]], true);
        c.fillStyle = tok("--accent-soft");
        c.fill();
      }
    }
    const tv = spec.top_view;
    if (tv) {
      this.path(evalOpen(tv.points, tv.corners, 0.25).dense);
      c.setLineDash([6, 4]);
      c.strokeStyle = ink;
      c.lineWidth = 1.3;
      c.stroke();
      c.setLineDash([]);
      const n = tv.points.length, on = (i: number) => sel.top?.kind === "outline" && sel.top.i === i;
      tv.points.forEach((q, i) => {
        const end = i === 0 || i === n - 1;
        this.dot(q, end ? 6 : 4, on(i) ? acc : end ? ink : tok("--panel"), ink, end || tv.corners.includes(i));
      });
    }
    spec.stations.forEach((st, i) => {
      const on = i === sel.station;
      this.path([[st.x, 0], [st.x, stationExtent(st).zHi]]);
      c.strokeStyle = on ? acc : muted;
      c.lineWidth = on ? 4 : 2.5;
      c.stroke();
    });
    drawFeatures(this, spec.features, "ledge", sel.top);
    const pend = this.app.store.newStation;
    if (pend !== null) {
      this.path([[pend, 0], [pend, 200]]);
      c.setLineDash([3, 4]);
      c.strokeStyle = acc;
      c.lineWidth = 2;
      c.stroke();
      c.setLineDash([]);
    }
    if (pend !== null) this.message(`Drawing the station at x = ${pend} in the section editor.`);
    else if (!spec.stations.length) this.message("Empty hold. Pick + Station, then click here where the first section goes.");
    if (this.pendingGroove) {
      this.path(this.pendingGroove);
      c.strokeStyle = tok("--accent2");
      c.lineWidth = 2;
      c.stroke();
    }
  }
}
