// Turns untrusted spec JSON (a saved draft, an imported file) into something the editor can open.
import { ApiError, api } from "../api/client";
import type { HoldSpec } from "../api/types.gen";
import { fromSpec } from "./model";

/** The spec in the current format, or null if it can't be opened. Older shapes are converted by the
 *  server (one definition of the format); with the server unreachable the spec is used as it is. */
export async function loadable(raw: unknown): Promise<HoldSpec | null> {
  if (!raw || typeof raw !== "object" || !Array.isArray((raw as HoldSpec).stations)) return null;
  let s = raw as HoldSpec;
  try {
    s = await api.migrate(s);
  } catch (e) {
    if (e instanceof ApiError) return null; // the server read it and it isn't a hold spec
  }
  try {
    fromSpec(s);
    return s;
  } catch {
    return null;
  }
}
