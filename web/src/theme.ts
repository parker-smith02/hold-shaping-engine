// Canvas drawing reads the same CSS custom properties as the DOM, so both themes stay in sync.
const cache = new Map<string, string>();
let cacheKey = "";

export function tok(name: string): string {
  const key = `${document.documentElement.dataset.theme ?? ""}|${matchMedia("(prefers-color-scheme: dark)").matches}`;
  if (key !== cacheKey) {
    cache.clear();
    cacheKey = key;
  }
  let v = cache.get(name);
  if (v === undefined) {
    v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    cache.set(name, v);
  }
  return v;
}

export function onThemeChange(fn: () => void): void {
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", fn);
  new MutationObserver(fn).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
}
