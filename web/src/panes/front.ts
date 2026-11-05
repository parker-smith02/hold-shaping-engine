// Front view (x, y on the wall): loose outline, stations, screws, face features, pinned notes.
import { evalClosed, nearestSegment, type Vec2 } from "../geometry/curves";
import { sortStations, stationExtent } from "../spec/edit";
import type { Hit } from "../state/store";
import { tok } from "../theme";
import { drawFeatures, hitFeature } from "./features";
import { Pane, type DragHandler } from "./pane";

const snapX = (x: number) => Math.round(x * 2) / 2;

export class FrontPane extends Pane {
  pendingGroove: Vec2[] | null = null;

  tool(): string {
    return this.app.store.tools.front;
  }

  private hit(w: Vec2): Hit | null {
    const { spec } = this.app.store;
    const P = spec.front_view?.points ?? [];
    for (let i = 0; i < P.length; i++) if (this.near(P[i], w)) return { kind: "outline", i };
    for (let i = 0; i < spec.mounting.screws.length; i++) if (this.near(spec.mounting.screws[i], w, 11)) return { kind: "screw", i };
    for (let i = 0; i < spec.notes.length; i++) {
      const n = spec.notes[i];
      if (n.anchor.view === "front" && this.near(n.anchor.at, w, 10)) return { kind: "note", i };
    }
    const f = hitFeature(this, spec.features, "front", w);
    if (f) return f;
    for (let i = 0; i < spec.stations.length; i++) {
      const e = stationExtent(spec.stations[i]), x = spec.stations[i].x;
      if (Math.abs((x - w[0]) * this.sc) < 7 && w[1] > e.yLo - 3 && w[1] < e.yHi + 3) return { kind: "station", i };
    }
    return null;
  }

  protected onDown(w: Vec2): DragHandler | null {
    const store = this.app.store, t = store.tools.front;
    if (t === "select") {
      const h = this.hit(w);
      store.select(h?.kind === "station" ? { front: h, station: h.i, point: null } : { front: h });
      if (!h) return null;
      const tracked = h.kind === "station" ? store.spec.stations[h.i] : null;
      return {
        move: (p) => store.mutate((s) => {
          if (h.kind === "outline") s.front_view!.points[h.i] = [p[0], p[1]];
          else if (h.kind === "station") s.stations[h.i].x = snapX(p[0]);
          else if (h.kind === "screw") s.mounting.screws[h.i] = [p[0], p[1]];
          else if (h.kind === "dent") (s.features[h.i] as { center: number[] }).center = [p[0], p[1]];
          else if (h.kind === "groove") (s.features[h.i] as { path: number[][] }).path[h.j] = [p[0], p[1]];
          else if (h.kind === "note") s.notes[h.i].anchor.at = [p[0], p[1]];
        }, { commit: false }),
        up: (moved) => {
          if (!moved) return;
          if (tracked) {
            const idx = sortStations(store.spec, tracked);
            store.select({ station: idx, front: { kind: "station", i: idx } });
          }
          store.mutate(() => {});
        },
      };
    }
    if (t === "outline") {
      store.mutate((s) => {
        s.front_view ??= { points: [], strength: 0.5, corners: [] };
        const P = s.front_view.points;
        if (P.length < 3) P.push([w[0], w[1]]);
        else P.splice(nearestSegment(P, w, true).index, 0, [w[0], w[1]]);
      });
      return null;
    }
    if (t === "station") {
      void this.app.addStationAt(snapX(w[0]));
      return null;
    }
    if (t === "screw") {
      store.mutate((s) => s.mounting.screws.push([w[0], w[1]]));
      store.select({ front: { kind: "screw", i: store.spec.mounting.screws.length - 1 } });
      return null;
    }
    if (t === "dent") {
      store.mutate((s) => s.features.push({ type: "dent", surface: "front", center: [w[0], w[1]], size: [8, 8, 4], depth: 1.5, note: "" }));
      store.select({ front: { kind: "dent", i: store.spec.features.length - 1 } });
      store.setTool("front", "select");
      return null;
    }
    if (t === "groove") {
      (this.pendingGroove ??= []).push([w[0], w[1]]);
      this.app.requestDraw();
      return null;
    }
    if (t === "note") {
      store.mutate((s) => s.notes.push({ anchor: { view: "front", at: [w[0], w[1]] }, text: "" }));
      store.select({ front: { kind: "note", i: store.spec.notes.length - 1 } });
      store.setTool("front", "select");
      return null;
    }
    return null;
  }

  protected override onDblClick(w: Vec2): void {
    const store = this.app.store;
    if (store.tools.front === "groove" && this.pendingGroove) {
      this.finishGroove();
      return;
    }
    const P = store.spec.front_view?.points;
    if (store.tools.front === "select" && P && P.length >= 3) {
      const r = nearestSegment(P, w, true);
      if (r.dist * this.sc < 10) {
        store.mutate((s) => s.front_view!.points.splice(r.index, 0, [w[0], w[1]]));
        store.select({ front: { kind: "outline", i: r.index } });
      }
    }
  }

  finishGroove(): void {
    const store = this.app.store, path = this.pendingGroove;
    this.pendingGroove = null;
    if (path && path.length >= 2) {
      store.mutate((s) => s.features.push({ type: "groove", surface: "front", path, width: 8, depth: 0.7, note: "" }));
      store.select({ front: { kind: "groove", i: store.spec.features.length - 1, j: 0 } });
    }
    store.setTool("front", "select");
  }

  fitView(): void {
    const { spec } = this.app.store;
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    const add = (x: number, y: number) => {
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    };
    for (const st of spec.stations) {
      const e = stationExtent(st);
      add(st.x, e.yLo);
      add(st.x, e.yHi);
    }
    spec.front_view?.points.forEach((p) => add(p[0], p[1]));
    const d = this.app.preview.state.data;
    if (d) {
      add(d.loft.x_min, y0);
      add(d.loft.x_max, y0);
    }
    this.fitTo(x0, x1, y0, y1);
  }

  draw(): void {
    const { spec, sel } = this.app.store, c = this.ctx;
    this.clear();
    this.drawUnderlay();
    this.grid();
    const acc = tok("--accent"), acc2 = tok("--accent2"), ink = tok("--ink"), muted = tok("--muted");
    const d = this.app.preview.state.data;
    if (d) {
      const { x, y_lo, y_hi } = d.extents;
      this.path([...x.map((v, i) => [v, y_hi[i]]), ...x.map((v, i) => [v, y_lo[i]]).reverse()], true);
      c.fillStyle = tok("--accent-soft");
      c.fill();
    }
    const fv = spec.front_view;
    if (fv && fv.points.length) {
      if (fv.points.length >= 3) {
        this.path(evalClosed(fv.points, fv.corners, 0.25), true);
        c.setLineDash([6, 4]);
        c.strokeStyle = ink;
        c.lineWidth = 1.3;
        c.stroke();
        c.setLineDash([]);
      }
      fv.points.forEach((q, i) => this.dot(q, 4, sel.front?.kind === "outline" && sel.front.i === i ? acc : tok("--panel"), ink, fv.corners.includes(i)));
    }
    spec.stations.forEach((st, i) => {
      const e = stationExtent(st), on = i === sel.station;
      this.path([[st.x, e.yLo], [st.x, e.yHi]]);
      c.strokeStyle = on ? acc : muted;
      c.lineWidth = on ? 4 : 2.5;
      c.stroke();
      this.text([st.x, e.yHi], `${Math.round(st.x * 100) / 100}`, on ? acc : muted, -8, -6);
    });
    const { screws, countersink_dia, hole_dia } = spec.mounting;
    screws.forEach((q, i) => {
      const [sx, sy] = this.toScreen(q[0], q[1]);
      c.beginPath();
      c.arc(sx, sy, (countersink_dia / 2) * this.sc, 0, Math.PI * 2);
      c.strokeStyle = sel.front?.kind === "screw" && sel.front.i === i ? acc : ink;
      c.lineWidth = 1.4;
      c.stroke();
      c.beginPath();
      c.arc(sx, sy, (hole_dia / 2) * this.sc, 0, Math.PI * 2);
      c.fillStyle = ink;
      c.fill();
    });
    drawFeatures(this, spec.features, "front", sel.front);
    spec.notes.forEach((n, i) => {
      if (n.anchor.view !== "front") return;
      const on = sel.front?.kind === "note" && sel.front.i === i;
      this.dot(n.anchor.at, 5, on ? acc : acc2, null, true);
      this.text(n.anchor.at, (n.text || "note").slice(0, 40), on ? acc : acc2, 8, 4);
    });
    if (this.pendingGroove) {
      this.path(this.pendingGroove);
      c.strokeStyle = acc2;
      c.lineWidth = 2;
      c.stroke();
      this.pendingGroove.forEach((q) => this.dot(q, 3, acc2, null));
    }
  }
}
