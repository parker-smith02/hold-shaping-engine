// Full build from the editor: submit a job, poll its status, show the verification images and report.
import { ApiError, api } from "../api/client";
import type { BuildStatus } from "../api/types.gen";
import { $, h } from "../dom";
import type { Store } from "../state/store";

interface StationReport {
  x: number;
  deviation_mm: { max: number; mean: number; p95: number };
  cuts_screw: boolean;
}

export class BuildPanel {
  private polling: ReturnType<typeof setTimeout> | null = null;

  constructor(private store: Store, private toast: (m: string) => void) {
    $("#btnBuild").addEventListener("click", () => void this.start());
  }

  async start(): Promise<void> {
    const btn = $<HTMLButtonElement>("#btnBuild");
    btn.disabled = true;
    try {
      const st = await api.submitBuild(this.store.toSpec());
      this.render(st);
      this.poll(st.id);
    } catch (e) {
      btn.disabled = false;
      const msg = e instanceof ApiError ? `${e.body.error}${e.issues.length ? `: ${e.issues[0].message}` : ""}` : (e as Error).message;
      this.toast(`Build not started. ${msg}`);
    }
  }

  private poll(id: string): void {
    if (this.polling) clearTimeout(this.polling);
    this.polling = setTimeout(async () => {
      try {
        const st = await api.getBuild(id);
        this.render(st);
        if (st.state === "queued" || st.state === "running") this.poll(id);
        else $<HTMLButtonElement>("#btnBuild").disabled = false;
      } catch {
        this.poll(id);
      }
    }, 1000);
  }

  private render(st: BuildStatus): void {
    $("#buildState").textContent = `${st.name} · ${st.state}`;
    const body = $("#buildBody");
    const log = h("pre", { class: "build-log", text: (st.log ?? []).slice(-6).join("\n") });
    if (st.state === "failed") {
      body.replaceChildren(h("div", { class: "issue", text: st.error ?? "Build failed." }), log);
      return;
    }
    if (st.state !== "done") {
      body.replaceChildren(h("p", { class: "help", text: st.state === "queued" ? "Waiting for the build worker…" : "Building the SDF and meshing…" }), log);
      return;
    }
    const rep = st.report as { mesh: { watertight: boolean; size_mm: number[]; volume_cm3: number }; stations: StationReport[]; elapsed_s: number } | null;
    const url = (f: string) => api.buildFileUrl(st.id, f);
    const worst = rep ? Math.max(...rep.stations.filter((s) => !s.cuts_screw).map((s) => s.deviation_mm.max)) : NaN;
    const parts: (HTMLElement | null)[] = [
      h("div", { class: "row" },
        h("a", { href: url("hold.stl"), download: `${st.name}.stl`, text: "Download STL" }),
        h("a", { href: url("report.md"), target: "_blank", text: "report.md" }),
        rep ? h("span", { class: "mono muted", text: `${rep.mesh.size_mm.join(" × ")} mm · ${rep.mesh.volume_cm3} cm³ · ${rep.elapsed_s} s · watertight ${rep.mesh.watertight ? "yes" : "NO"}` }) : null),
      rep ? h("p", { class: "help", text: `Worst station deviation from your splines (excluding screw cuts): ${worst.toFixed(2)} mm.` }) : null,
      h("div", { class: "build-imgs" },
        h("img", { src: url("overlay.png"), alt: "Drawn sections (black) over built sections (blue) at every station" }),
        h("img", { src: url("preview.png"), alt: "Shaded views of the built hold" })),
    ];
    body.replaceChildren(...parts.filter((p): p is HTMLElement => p !== null));
  }
}
