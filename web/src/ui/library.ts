// Hold library: the server's holds/ directory (one JSON file per hold, tracked in git).
import { ApiError, api } from "../api/client";
import { $, armed, h } from "../dom";
import type { Store } from "../state/store";

export class Library {
  constructor(private store: Store, private toast: (m: string) => void) {
    $("#btnLibRefresh").addEventListener("click", () => void this.refresh());
  }

  async refresh(): Promise<void> {
    const el = $("#libList"), status = $("#libStatus");
    try {
      const holds = await api.listHolds();
      status.textContent = `${holds.length} in holds/`;
      if (!holds.length) {
        el.replaceChildren(h("p", { class: "help", text: "No saved holds yet. Save writes the current hold to holds/<name>.json." }));
        return;
      }
      el.replaceChildren(...holds.map((hold) => {
        const del = h("button", { type: "button", class: "danger", text: "Delete" });
        armed(del, "Delete", async () => {
          await api.deleteHold(hold.name);
          this.toast(`Deleted holds/${hold.name}.json`);
          void this.refresh();
        });
        return h("div", { class: "lib-item" },
          h("span", { class: "nm", text: hold.name, title: hold.description }),
          h("span", { class: "when", text: `${hold.stations} st · ${new Date(hold.updated).toLocaleDateString(undefined, { month: "short", day: "numeric" })}` }),
          h("button", { type: "button", text: "Open", on: { click: () => void this.open(hold.name) } }),
          del);
      }));
    } catch (e) {
      status.textContent = "unavailable";
      el.replaceChildren(h("p", { class: "help", text: `Couldn't list holds: ${(e as Error).message}` }));
    }
  }

  async open(name: string): Promise<void> {
    try {
      this.store.load(await api.getHold(name));
      this.toast(`Opened holds/${name}.json`);
    } catch (e) {
      this.toast(`Couldn't open ${name}: ${(e as Error).message}`);
    }
  }

  async save(): Promise<void> {
    const spec = this.store.toSpec();
    try {
      const res = await api.putHold(spec.name, spec);
      const errs = res.issues.filter((i) => i.level === "error").length;
      this.toast(`Saved holds/${res.name}.json${errs ? ` (${errs} error${errs > 1 ? "s" : ""} to fix before building)` : ""}`);
      void this.refresh();
    } catch (e) {
      this.toast(e instanceof ApiError ? `Not saved: ${e.body.error}` : `Not saved: ${(e as Error).message}`);
    }
  }
}
