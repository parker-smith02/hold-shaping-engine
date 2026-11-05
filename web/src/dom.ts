// Minimal DOM construction helper (no framework: the UI is canvases plus a few small panels).
type Props = Record<string, unknown> & { class?: string; text?: string; on?: Record<string, (e: Event) => void> };

export function h<K extends keyof HTMLElementTagNameMap>(tag: K, props: Props = {}, ...children: (Node | string | null | false)[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v === undefined || v === null) continue;
    if (k === "class") el.className = String(v);
    else if (k === "text") el.textContent = String(v);
    else if (k === "on") for (const [ev, fn] of Object.entries(v as Record<string, (e: Event) => void>)) el.addEventListener(ev, fn);
    else if (k in el) (el as unknown as Record<string, unknown>)[k] = v;
    else el.setAttribute(k, String(v));
  }
  for (const c of children) if (c !== null && c !== false) el.append(c);
  return el;
}

export const $ = <T extends HTMLElement = HTMLElement>(sel: string): T => {
  const el = document.querySelector<T>(sel);
  if (!el) throw new Error(`missing element ${sel}`);
  return el;
};

/** Two-click confirmation for destructive buttons (no modal dialogs). */
export function armed(btn: HTMLButtonElement, label: string, action: () => void): void {
  btn.addEventListener("click", () => {
    if (btn.dataset.armed) {
      delete btn.dataset.armed;
      btn.textContent = label;
      action();
      return;
    }
    btn.dataset.armed = "1";
    btn.textContent = "Click again to confirm";
    setTimeout(() => {
      delete btn.dataset.armed;
      btn.textContent = label;
    }, 2500);
  });
}
