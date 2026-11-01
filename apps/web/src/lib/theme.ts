/**
 * Light/dark theme, same contract as the other 3m4 apps: follows the system
 * preference until the user picks one; the choice persists in localStorage
 * (`3m4.theme`) and is applied before first paint by the inline script in
 * root.tsx. Styling reacts to `data-theme` on <html> (see global.css).
 */
export type Theme = "light" | "dark";
export const THEME_STORAGE_KEY = "3m4.theme";

export function getTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* ignore */
  }
  if (typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }
  return "light";
}

export function setTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* ignore */
  }
  document.documentElement.dataset.theme = theme;
}
