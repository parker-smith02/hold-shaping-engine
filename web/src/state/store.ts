// Single source of editor state: the spec being edited, selection, active tools and undo history.
// Mutations go through `mutate`; listeners get the kind of change so the UI updates only what moved.
import type { HoldSpec } from "../api/types.gen";
import { fromSpec, toSpec, type EditableSpec } from "../spec/model";

export type PaneName = "front" | "top" | "section";
export type FrontTool = "select" | "station" | "screw" | "dent" | "groove" | "note" | "image";
export type TopTool = "select" | "station" | "dent" | "groove" | "image";
export type SectionTool = "select" | "draw" | "image";

export type Hit =
  | { kind: "outline"; i: number; edge?: "upper" | "lower" } // edge: front view only
  | { kind: "station"; i: number }
  | { kind: "screw"; i: number }
  | { kind: "dent"; i: number }
  | { kind: "groove"; i: number; j: number }
  | { kind: "note"; i: number };

export interface Selection {
  station: number;
  point: number | null;
  front: Hit | null;
  top: Hit | null;
}

export type Change = "spec" | "selection" | "tools" | "load" | "history";
type Listener = (changes: Set<Change>) => void;

const HISTORY_LIMIT = 200;

export class Store {
  spec: EditableSpec;
  sel: Selection = { station: 0, point: null, front: null, top: null };
  tools: { front: FrontTool; top: TopTool; section: SectionTool } = { front: "select", top: "select", section: "select" };
  /** x of a station being drawn from scratch in the section editor; it joins the spec when finished. */
  newStation: number | null = null;
  private past: string[] = [];
  private future: string[] = [];
  private committed: string;
  private listeners = new Set<Listener>();
  private pending = new Set<Change>();
  private scheduled = false;

  constructor(initial: HoldSpec) {
    this.spec = fromSpec(initial);
    this.committed = JSON.stringify(this.spec);
    this.sel.station = Math.floor(this.spec.stations.length / 2);
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  /** Coalesce notifications to one per microtask so a burst of edits re-renders once. */
  emit(...changes: Change[]): void {
    changes.forEach((c) => this.pending.add(c));
    if (this.scheduled) return;
    this.scheduled = true;
    queueMicrotask(() => {
      this.scheduled = false;
      const batch = this.pending;
      this.pending = new Set();
      this.listeners.forEach((fn) => fn(batch));
    });
  }

  /** Apply an edit. `commit: false` is for continuous drags; call commit() when the drag ends. */
  mutate(fn: (spec: EditableSpec) => void, opts: { commit?: boolean } = {}): void {
    fn(this.spec);
    this.clampSelection();
    if (opts.commit ?? true) this.commit();
    this.emit("spec");
  }

  commit(): void {
    const now = JSON.stringify(this.spec);
    if (now === this.committed) return;
    this.past.push(this.committed);
    if (this.past.length > HISTORY_LIMIT) this.past.shift();
    this.future = [];
    this.committed = now;
    this.emit("history");
  }

  get canUndo(): boolean {
    return this.past.length > 0;
  }
  get canRedo(): boolean {
    return this.future.length > 0;
  }

  undo(): void {
    const prev = this.past.pop();
    if (prev === undefined) return;
    this.future.push(this.committed);
    this.restore(prev);
  }

  redo(): void {
    const next = this.future.pop();
    if (next === undefined) return;
    this.past.push(this.committed);
    this.restore(next);
  }

  private restore(json: string): void {
    this.spec = JSON.parse(json);
    this.committed = json;
    this.sel.point = null;
    this.sel.front = this.sel.top = null;
    this.clampSelection();
    this.emit("spec", "selection", "history");
  }

  /** Replace the whole spec (open from library, import, new). Undoable. */
  load(s: HoldSpec): void {
    this.spec = fromSpec(s);
    this.sel = { station: Math.floor(this.spec.stations.length / 2), point: null, front: null, top: null };
    this.newStation = null;
    this.commit();
    this.emit("load", "spec", "selection");
  }

  select(patch: Partial<Selection>): void {
    Object.assign(this.sel, patch);
    this.clampSelection();
    this.emit("selection");
  }

  setNewStation(x: number | null): void {
    this.newStation = x;
    this.emit("tools");
  }

  setTool<P extends PaneName>(pane: P, tool: Store["tools"][P]): void {
    this.tools[pane] = tool;
    this.emit("tools");
  }

  toSpec(): HoldSpec {
    return toSpec(this.spec);
  }

  get station() {
    return this.spec.stations[this.sel.station];
  }

  private clampSelection(): void {
    const n = this.spec.stations.length;
    this.sel.station = Math.max(0, Math.min(n - 1, this.sel.station));
    const st = this.spec.stations[this.sel.station];
    if (this.sel.point !== null && (!st || this.sel.point >= st.points.length)) this.sel.point = null;
  }
}
