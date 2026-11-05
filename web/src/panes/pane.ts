// Base class for the 2D drafting panes: world (mm) <-> screen transform with optional rotation,
// pan / zoom, grid, reference-image underlay, and pointer dispatch to the subclass.
import type { Vec2 } from "../geometry/curves";
import type { PreviewSync } from "../state/preview";
import type { Store } from "../state/store";
import { tok } from "../theme";

export interface Ctx {
  store: Store;
  preview: PreviewSync;
  toast(msg: string): void;
  addStationAt(x: number): Promise<void>;
  requestDraw(): void;
}

export interface DragHandler {
  move(w: Vec2, e: PointerEvent): void;
  up(moved: boolean): void;
}

export interface Underlay {
  img: HTMLImageElement;
  x: number; // world position of the image's top-left corner
  y: number;
  mmPerPx: number;
  opacity: number;
}

type DragState =
  | { kind: "pan"; sx: number; sy: number; cx: number; cy: number }
  | { kind: "image"; w0: Vec2; x: number; y: number }
  | { kind: "handler"; h: DragHandler; moved: boolean };

export abstract class Pane {
  readonly ctx: CanvasRenderingContext2D;
  cx = 0;
  cy = 0;
  sc = 3; // px per mm
  rot = 0; // radians, positive = counter-clockwise on screen
  W = 1;
  H = 1;
  underlay: Underlay | null = null;
  hoverW: Vec2 | null = null;
  private drag: DragState | null = null;

  constructor(readonly cv: HTMLCanvasElement, protected app: Ctx) {
    const c = cv.getContext("2d");
    if (!c) throw new Error("2D canvas unavailable");
    this.ctx = c;
    new ResizeObserver(() => this.resize()).observe(cv.parentElement!);
    this.resize();
    cv.addEventListener("pointerdown", (e) => this.down(e));
    cv.addEventListener("pointermove", (e) => this.move(e));
    cv.addEventListener("pointerup", () => this.up());
    cv.addEventListener("pointercancel", () => this.up());
    cv.addEventListener("pointerleave", () => {
      this.hoverW = null;
      this.onHover(null);
    });
    cv.addEventListener("dblclick", (e) => this.onDblClick(this.toWorld(...this.xy(e))));
    cv.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.wheel(e);
    }, { passive: false });
    cv.addEventListener("contextmenu", (e) => e.preventDefault());
  }

  abstract tool(): string;
  protected abstract onDown(w: Vec2, e: PointerEvent): DragHandler | null;
  protected onDblClick(_w: Vec2): void {}
  protected onHover(_w: Vec2 | null): void {}
  abstract draw(): void;
  abstract fitView(): void;

  resize(): void {
    const r = this.cv.parentElement!.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.W = Math.max(1, r.width);
    this.H = Math.max(1, r.height);
    this.cv.width = Math.round(this.W * dpr);
    this.cv.height = Math.round(this.H * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.app.requestDraw();
  }

  toScreen(wx: number, wy: number): Vec2 {
    const dx = wx - this.cx, dy = wy - this.cy, c = Math.cos(this.rot), s = Math.sin(this.rot);
    return [this.W / 2 + (dx * c - dy * s) * this.sc, this.H / 2 - (dx * s + dy * c) * this.sc];
  }

  toWorld(sx: number, sy: number): Vec2 {
    const rx = (sx - this.W / 2) / this.sc, ry = -(sy - this.H / 2) / this.sc, c = Math.cos(this.rot), s = Math.sin(this.rot);
    return [this.cx + rx * c + ry * s, this.cy - rx * s + ry * c];
  }

  fitTo(x0: number, x1: number, y0: number, y1: number, pad = 0.12): void {
    this.cx = (x0 + x1) / 2;
    this.cy = (y0 + y1) / 2;
    const w = Math.max(x1 - x0, 1), h = Math.max(y1 - y0, 1);
    this.sc = Math.min(this.W / (w * (1 + 2 * pad)), this.H / (h * (1 + 2 * pad)));
    this.app.requestDraw();
  }

  /** Screen-space proximity test (px), so hit targets stay the same size at any zoom. */
  near(p: readonly number[], w: Vec2, px = 9): boolean {
    const a = this.toScreen(p[0], p[1]), b = this.toScreen(w[0], w[1]);
    return Math.hypot(a[0] - b[0], a[1] - b[1]) <= px;
  }

  loadUnderlay(file: File): void {
    const img = new Image();
    img.onload = () => {
      const [x0, y1] = this.toWorld(0, 0), [x1, y0] = this.toWorld(this.W, this.H);
      const mm = Math.min((x1 - x0) / img.width, (y1 - y0) / img.height) * 0.9;
      this.underlay = { img, x: x0 + (x1 - x0 - img.width * mm) / 2, y: y1 - (y1 - y0 - img.height * mm) / 2, mmPerPx: mm, opacity: 0.45 };
      this.app.requestDraw();
    };
    img.src = URL.createObjectURL(file);
  }

  // ---------------------------------------------------------------- pointer plumbing
  private xy(e: MouseEvent): Vec2 {
    const r = this.cv.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  private down(e: PointerEvent): void {
    this.cv.focus({ preventScroll: true });
    const [sx, sy] = this.xy(e);
    this.cv.setPointerCapture(e.pointerId);
    const w = this.toWorld(sx, sy);
    if (e.button === 1 || e.button === 2) {
      this.drag = { kind: "pan", sx, sy, cx: this.cx, cy: this.cy };
      return;
    }
    if (this.tool() === "image" && this.underlay) {
      this.drag = { kind: "image", w0: w, x: this.underlay.x, y: this.underlay.y };
      return;
    }
    const h = this.onDown(w, e);
    this.drag = h ? { kind: "handler", h, moved: false } : { kind: "pan", sx, sy, cx: this.cx, cy: this.cy };
  }

  private move(e: PointerEvent): void {
    const [sx, sy] = this.xy(e);
    const w = this.toWorld(sx, sy);
    this.hoverW = w;
    this.onHover(w);
    const d = this.drag;
    if (!d) return;
    if (d.kind === "pan") {
      const c = Math.cos(this.rot), s = Math.sin(this.rot);
      const rx = -(sx - d.sx) / this.sc, ry = (sy - d.sy) / this.sc;
      this.cx = d.cx + rx * c + ry * s;
      this.cy = d.cy - rx * s + ry * c;
      this.app.requestDraw();
    } else if (d.kind === "image" && this.underlay) {
      this.underlay.x = d.x + (w[0] - d.w0[0]);
      this.underlay.y = d.y + (w[1] - d.w0[1]);
      this.app.requestDraw();
    } else if (d.kind === "handler") {
      d.moved = true;
      d.h.move(w, e);
    }
  }

  private up(): void {
    const d = this.drag;
    this.drag = null;
    if (d?.kind === "handler") d.h.up(d.moved);
  }

  private wheel(e: WheelEvent): void {
    const [sx, sy] = this.xy(e);
    const f = Math.exp(-e.deltaY * 0.0015);
    if (this.tool() === "image" && this.underlay) {
      this.underlay.mmPerPx *= f;
      this.app.requestDraw();
      return;
    }
    const w0 = this.toWorld(sx, sy);
    this.sc = Math.max(0.3, Math.min(80, this.sc * f));
    const w1 = this.toWorld(sx, sy);
    this.cx += w0[0] - w1[0];
    this.cy += w0[1] - w1[1];
    this.app.requestDraw();
  }

  // ---------------------------------------------------------------- drawing helpers
  clear(): void {
    this.ctx.clearRect(0, 0, this.W, this.H);
  }

  drawUnderlay(): void {
    const u = this.underlay;
    if (!u) return;
    const c = this.ctx, [sx, sy] = this.toScreen(u.x, u.y), s = u.mmPerPx * this.sc;
    c.save();
    c.globalAlpha = u.opacity;
    c.translate(sx, sy);
    c.rotate(-this.rot);
    c.drawImage(u.img, 0, 0, u.img.width * s, u.img.height * s);
    c.restore();
  }

  grid(labels = true): void {
    const c = this.ctx;
    const corners = ([[0, 0], [this.W, 0], [0, this.H], [this.W, this.H]] as Vec2[]).map((p) => this.toWorld(...p));
    const x0 = Math.min(...corners.map((p) => p[0])), x1 = Math.max(...corners.map((p) => p[0]));
    const y0 = Math.min(...corners.map((p) => p[1])), y1 = Math.max(...corners.map((p) => p[1]));
    const minor = this.sc > 9 ? 1 : this.sc > 2.2 ? 5 : 10, major = this.sc > 0.9 ? 10 : 50;
    c.lineWidth = 1;
    for (const [step, col] of [[minor, tok("--grid")], [major, tok("--line")]] as [number, string][]) {
      c.strokeStyle = col;
      c.beginPath();
      for (let x = Math.ceil(x0 / step) * step; x <= x1; x += step) {
        const a = this.toScreen(x, y0), b = this.toScreen(x, y1);
        c.moveTo(a[0], a[1]);
        c.lineTo(b[0], b[1]);
      }
      for (let y = Math.ceil(y0 / step) * step; y <= y1; y += step) {
        const a = this.toScreen(x0, y), b = this.toScreen(x1, y);
        c.moveTo(a[0], a[1]);
        c.lineTo(b[0], b[1]);
      }
      c.stroke();
    }
    if (labels && this.rot === 0) {
      c.fillStyle = tok("--muted");
      c.font = `10px ${tok("--font-data")}`;
      const lx = major * Math.max(1, Math.ceil(30 / (major * this.sc)));
      const ly = major * Math.max(1, Math.ceil(18 / (major * this.sc)));
      for (let x = Math.ceil(x0 / lx) * lx; x <= x1; x += lx) c.fillText(String(x), this.toScreen(x, 0)[0] + 2, 11);
      for (let y = Math.ceil(y0 / ly) * ly; y <= y1; y += ly) c.fillText(String(y), 3, this.toScreen(0, y)[1] - 2);
    }
  }

  path(pts: readonly (readonly number[])[], close = false): void {
    const c = this.ctx;
    c.beginPath();
    pts.forEach((p, i) => {
      const [sx, sy] = this.toScreen(p[0], p[1]);
      if (i) c.lineTo(sx, sy);
      else c.moveTo(sx, sy);
    });
    if (close) c.closePath();
  }

  dot(p: readonly number[], r: number, fill: string | null, stroke: string | null, square = false): void {
    const c = this.ctx, [sx, sy] = this.toScreen(p[0], p[1]);
    c.beginPath();
    if (square) c.rect(sx - r, sy - r, 2 * r, 2 * r);
    else c.arc(sx, sy, r, 0, Math.PI * 2);
    if (fill) {
      c.fillStyle = fill;
      c.fill();
    }
    if (stroke) {
      c.strokeStyle = stroke;
      c.lineWidth = 1.5;
      c.stroke();
    }
  }

  text(p: readonly number[], s: string, col: string, dx = 6, dy = -6, font?: string): void {
    const c = this.ctx, [sx, sy] = this.toScreen(p[0], p[1]);
    c.fillStyle = col;
    c.font = font ?? `11px ${tok("--font-data")}`;
    c.fillText(s, sx + dx, sy + dy);
  }
}
