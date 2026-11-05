// Drawing of dents and grooves, shared by the front (face) and top (ledge) panes.
import type { Hit } from "../state/store";
import type { Feature } from "../spec/model";
import { tok } from "../theme";
import type { Pane } from "./pane";

export function drawFeatures(p: Pane, features: Feature[], surface: "front" | "ledge", sel: Hit | null): void {
  const c = p.ctx, acc = tok("--accent"), acc2 = tok("--accent2");
  features.forEach((f, i) => {
    if (f.surface !== surface) return;
    const on = !!sel && (sel.kind === "dent" || sel.kind === "groove") && sel.i === i;
    const col = on ? acc : acc2;
    if (f.type === "dent") {
      const size = f.size ?? [8, 8, 4];
      const [sx, sy] = p.toScreen(f.center[0], f.center[1]);
      const rx = size[0] * p.sc, ry = (surface === "front" ? size[1] : size[2]) * p.sc;
      c.beginPath();
      c.ellipse(sx, sy, rx, ry, -p.rot, 0, Math.PI * 2);
      c.strokeStyle = col;
      c.setLineDash([3, 3]);
      c.lineWidth = 1.5;
      c.stroke();
      c.setLineDash([]);
      p.dot(f.center, 3.5, col, null);
      p.text(f.center, `${f.depth > 0 ? "dent" : "bump"} ${Math.abs(f.depth)} mm`, col, 8, -8);
    } else {
      const width = f.width ?? 6;
      p.path(f.path);
      c.strokeStyle = col;
      c.globalAlpha = 0.18;
      c.lineWidth = Math.max(2, width * p.sc);
      c.lineCap = "round";
      c.stroke();
      c.globalAlpha = 1;
      p.path(f.path);
      c.lineWidth = 1.5;
      c.stroke();
      c.lineCap = "butt";
      f.path.forEach((q) => p.dot(q, 3.5, col, null));
      p.text(f.path[0], `${f.depth > 0 ? "groove" : "ridge"} ${Math.abs(f.depth)} mm`, col, 8, 12);
    }
  });
}

export function hitFeature(p: Pane, features: Feature[], surface: "front" | "ledge", w: [number, number]): Hit | null {
  for (let i = 0; i < features.length; i++) {
    const f = features[i];
    if (f.surface !== surface) continue;
    if (f.type === "dent" && p.near(f.center, w, 10)) return { kind: "dent", i };
    if (f.type === "groove") for (let j = 0; j < f.path.length; j++) if (p.near(f.path[j], w)) return { kind: "groove", i, j };
  }
  return null;
}
