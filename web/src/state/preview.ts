// Keeps the server-computed preview in step with the spec: debounced, one request in flight,
// stale responses dropped, last good geometry kept (and marked stale) while the spec has errors.
// A spec that can't be previewed yet (e.g. fewer than two stations) is never sent: `hint` says what's missing.
import { ApiError, api, decodeMesh } from "../api/client";
import type { HoldSpec, Issue, PreviewResponse } from "../api/types.gen";

export interface PreviewState {
  data: PreviewResponse | null;
  mesh: { positions: Float32Array; indices: Uint32Array } | null;
  issues: Issue[];
  error: string | null;
  stale: boolean;
  pending: boolean;
  latencyMs: number | null;
  hint: string | null; // why there is no preview yet (nothing drawn); not an error
}

const IDLE: PreviewState = { data: null, mesh: null, issues: [], error: null, stale: false, pending: false, latencyMs: null, hint: null };

export class PreviewSync {
  state: PreviewState = { ...IDLE };
  private seq = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private inflight: AbortController | null = null;
  private listeners = new Set<(s: PreviewState) => void>();

  /** `notReady` returns a hint when the spec can't be previewed yet, or null when it can. */
  constructor(private getSpec: () => HoldSpec, private notReady: (s: HoldSpec) => string | null = () => null,
              private debounceMs = 40) {}

  subscribe(fn: (s: PreviewState) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(): void {
    this.listeners.forEach((fn) => fn(this.state));
  }

  request(immediate = false): void {
    if (this.timer) clearTimeout(this.timer);
    this.state.pending = true;
    this.timer = setTimeout(() => void this.run(), immediate ? 0 : this.debounceMs);
  }

  private async run(): Promise<void> {
    const id = ++this.seq;
    this.inflight?.abort();
    const spec = this.getSpec(), hint = this.notReady(spec);
    if (hint) {
      this.inflight = null;
      this.state = { ...IDLE, hint };
      this.emit();
      return;
    }
    const ctl = new AbortController();
    this.inflight = ctl;
    const t0 = performance.now();
    try {
      const data = await api.preview(spec, ctl.signal);
      if (id !== this.seq) return;
      this.state = {
        data, mesh: decodeMesh(data.mesh), issues: data.issues, error: null, stale: false,
        pending: false, latencyMs: Math.round(performance.now() - t0), hint: null,
      };
    } catch (e) {
      if (id !== this.seq || (e instanceof DOMException && e.name === "AbortError")) return;
      const issues = e instanceof ApiError ? e.issues : [];
      const error = e instanceof ApiError ? e.body.error : `Can't reach the holdgen server (${(e as Error).message}). Is holdgen-server running?`;
      this.state = { ...this.state, issues, error, stale: this.state.data !== null, pending: false, hint: null };
    }
    this.emit();
  }
}
