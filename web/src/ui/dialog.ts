// Import / export of hold-spec/1 JSON.
import type { HoldSpec } from "../api/types.gen";
import { $ } from "../dom";
import type { Store } from "../state/store";

export function setupDialog(store: Store, toast: (m: string) => void): { open(mode: "import" | "export"): void } {
  const dlg = $<HTMLDialogElement>("#dlg"), text = $<HTMLTextAreaElement>("#dlgText");
  let mode: "import" | "export" = "export";

  const open = (m: "import" | "export") => {
    mode = m;
    $("#dlgTitle").textContent = m === "export" ? "Export hold spec" : "Import hold spec";
    $("#dlgHelp").textContent = m === "export"
      ? "The hold-spec/1 file the engine reads (holdgen build <file>)."
      : "Paste a hold-spec/1 file or choose one. The current hold stays in undo history.";
    text.value = m === "export" ? JSON.stringify(store.toSpec(), null, 2) : "";
    text.readOnly = m === "export";
    $("#dlgOk").hidden = m === "export";
    $("#dlgPick").hidden = m === "export";
    $("#dlgCopy").hidden = m !== "export";
    $("#dlgDownload").hidden = m !== "export";
    dlg.showModal();
  };

  $("#dlgPick").addEventListener("click", () => $<HTMLInputElement>("#dlgFile").click());
  $<HTMLInputElement>("#dlgFile").addEventListener("change", async (e) => {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) text.value = await f.text();
  });
  $("#dlgCopy").addEventListener("click", () => {
    navigator.clipboard.writeText(text.value).then(() => toast("Copied the spec."), () => {
      text.select();
      toast("Press Ctrl+C to copy the selected text.");
    });
  });
  $("#dlgDownload").addEventListener("click", () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text.value + "\n"], { type: "application/json" }));
    a.download = `${store.spec.name}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  });
  $("#dlgOk").addEventListener("click", () => {
    if (mode !== "import") return;
    try {
      const s = JSON.parse(text.value) as HoldSpec;
      if (!Array.isArray(s.stations)) throw new Error("no stations");
      store.load(s);
      dlg.close();
      toast(`Loaded ${s.name}.`);
    } catch {
      toast("That isn't a hold spec. Check it's JSON with a stations list.");
    }
  });
  return { open };
}
