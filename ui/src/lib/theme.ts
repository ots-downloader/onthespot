// Light/dark appearance. The backend `theme` setting is the source of truth;
// the browser copy only lets index.html paint the right mode before the
// config has loaded.

export type Appearance = "system" | "dark" | "light";

// Keep the key and the values in step with the inline script in index.html.
const STORAGE_KEY = "ots-theme";

/** Old or hand-edited configs can hold any text; treat the unknown as system. */
function toAppearance(value: unknown): Appearance {
  return value === "dark" || value === "light" ? value : "system";
}

/**
 * Point the page at an appearance. Light and dark set `data-theme` on <html>;
 * system removes it, and index.css then follows the OS.
 */
export function applyAppearance(value: unknown): void {
  const appearance = toAppearance(value);
  const root = document.documentElement;
  if (appearance === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", appearance);
  }
  try {
    localStorage.setItem(STORAGE_KEY, appearance);
  } catch {
    // Storage can be blocked; the setting still applies for this page load.
  }
}
