// Typed client for the holdgen server. Shapes come from types.gen.ts (generated from pydantic).
import type {
  BuildStatus, ErrorResponse, HoldList, HoldSpec, Issue, PreviewResponse, SaveResponse, SectionAtResponse,
  Station, ValidateResponse,
} from "./types.gen";

export class ApiError extends Error {
  constructor(public status: number, public body: ErrorResponse) {
    super(body.error);
  }
  get issues(): Issue[] {
    return this.body.issues ?? [];
  }
}

async function call<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, {
    method,
    signal,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { error: text || res.statusText };
  }
  if (!res.ok) {
    const err = (data && typeof data === "object" && "error" in data ? data : { error: res.statusText }) as ErrorResponse;
    throw new ApiError(res.status, err);
  }
  return data as T;
}

export const api = {
  validate: (spec: HoldSpec) => call<ValidateResponse>("POST", "/api/validate", { spec }),
  preview: (spec: HoldSpec, signal?: AbortSignal, step = 0.4, dx = 1.0) =>
    call<PreviewResponse>("POST", "/api/preview", { spec, step, dx }, signal),
  sectionAt: (spec: HoldSpec, x: number) =>
    call<SectionAtResponse>("POST", "/api/section-at", { spec, x }).then((r): Station => r.station),
  listHolds: () => call<HoldList>("GET", "/api/holds").then((r) => r.holds),
  /** The spec in the current hold-spec/1 shape (older drafts, files and imports are converted). */
  migrate: (spec: HoldSpec) => call<HoldSpec>("POST", "/api/migrate", { spec }),
  getHold: (name: string) => call<HoldSpec>("GET", `/api/holds/${encodeURIComponent(name)}`),
  putHold: (name: string, spec: HoldSpec) => call<SaveResponse>("PUT", `/api/holds/${encodeURIComponent(name)}`, spec),
  deleteHold: (name: string) => call<void>("DELETE", `/api/holds/${encodeURIComponent(name)}`),
  submitBuild: (spec: HoldSpec) => call<BuildStatus>("POST", "/api/builds", { spec }),
  getBuild: (id: string) => call<BuildStatus>("GET", `/api/builds/${encodeURIComponent(id)}`),
  buildFileUrl: (id: string, name: string) => `/api/builds/${encodeURIComponent(id)}/files/${encodeURIComponent(name)}`,
};

/** Decode the base64 little-endian mesh buffers of a PreviewResponse. */
export function decodeMesh(m: PreviewResponse["mesh"]): { positions: Float32Array; indices: Uint32Array } {
  const bytes = (b64: string) => {
    const s = atob(b64);
    const out = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
    return out.buffer;
  };
  if (new Uint8Array(new Uint16Array([1]).buffer)[0] !== 1) throw new Error("big-endian platforms are not supported");
  const positions = new Float32Array(bytes(m.positions));
  const indices = new Uint32Array(bytes(m.indices));
  if (positions.length !== m.vertex_count * 3 || indices.length !== m.triangle_count * 3) {
    throw new Error("preview mesh buffers don't match their declared sizes");
  }
  return { positions, indices };
}
