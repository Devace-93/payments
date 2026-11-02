/**
 * i18n runtime for the Qwik app.
 *
 * - The active locale lives in a context store (`I18nContext`) provided by the
 *   root layout; `tr(i18n, key)` translates against it.
 * - SSR always renders English. On the client the saved / browser locale is
 *   resolved, its catalog is lazy-loaded (one chunk per base language) and the
 *   store updates, re-rendering every `tr()` call site.
 * - Resolution per key: country variant → base language → English.
 * - Preferences persist in localStorage (`3m4.lang`), same key as the other
 *   3m4 apps. localStorage is per origin, so the choice does not travel by
 *   itself: pay.js opens the portal with `?lang=<locale>` (the host site's
 *   `3m4.lang`), which wins over the saved value and is persisted here; the
 *   accounts links (lib/api.ts) carry it onward the same way.
 */
import { createContextId, useContext } from "@builder.io/qwik";
import en, { type CatalogKey, type PartialCatalog } from "./catalog/en";
import { baseOf, DEFAULT_LANG, isRtl, LANG_STORAGE_KEY, matchLang, resolveLang } from "./langs";

export interface I18nState {
  lang: string;
  /** Merged strings for the active locale (base + country overrides). */
  strings: PartialCatalog;
}

export const I18nContext = createContextId<I18nState>("payments.i18n");

// One chunk per catalog file; Vite resolves the glob at build time.
const loaders = import.meta.glob<{ default: PartialCatalog }>(["./catalog/*.ts", "!./catalog/en.ts"]);

async function loadCatalog(lang: string): Promise<PartialCatalog> {
  const base = baseOf(lang);
  const merged: PartialCatalog = {};
  for (const name of [base, lang]) {
    if (name === "en") continue;
    const loader = loaders[`./catalog/${name}.ts`];
    if (!loader) continue;
    try {
      Object.assign(merged, (await loader()).default);
    } catch {
      /* a broken catalog must never break the page */
    }
  }
  return merged;
}

function applyDocumentLang(lang: string): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = lang;
  document.documentElement.dir = isRtl(lang) ? "rtl" : "ltr";
}

/** `?lang=` of the current page, validated against LANGS (`null` when absent or unknown). */
function langFromQuery(): string | null {
  if (typeof location === "undefined") return null;
  try {
    return matchLang(new URLSearchParams(location.search).get("lang"));
  } catch {
    return null;
  }
}

/**
 * Resolve the locale on the client and load its catalog into the store:
 * 1. `?lang=` (handed over by another 3m4 site) — persisted to `3m4.lang`,
 * 2. the saved `3m4.lang`, 3. `navigator.language`, 4. English.
 */
export async function initI18n(store: I18nState): Promise<void> {
  const fromQuery = langFromQuery();
  if (fromQuery) {
    await setLang(store, fromQuery, true);
    return;
  }
  let saved: string | null = null;
  try {
    saved = localStorage.getItem(LANG_STORAGE_KEY);
  } catch {
    /* storage unavailable */
  }
  const lang = resolveLang(saved, typeof navigator !== "undefined" ? navigator.language : undefined);
  await setLang(store, lang, false);
}

export async function setLang(store: I18nState, lang: string, persist = true): Promise<void> {
  if (persist) {
    try {
      localStorage.setItem(LANG_STORAGE_KEY, lang);
    } catch {
      /* ignore */
    }
  }
  store.strings = lang === DEFAULT_LANG ? {} : await loadCatalog(lang);
  store.lang = lang;
  applyDocumentLang(lang);
}

export type Params = Record<string, string | number>;

export function translate(store: I18nState, key: CatalogKey, params?: Params): string {
  let text: string = store.strings[key] ?? en[key] ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) text = text.split(`{${k}}`).join(String(v));
  }
  return text;
}

/**
 * Usage in components:
 *
 *   const i18n = useI18n();
 *   <h1>{tr(i18n, "pay.meTitle")}</h1>
 *
 * `tr` is a module function on purpose: Qwik's optimizer treats values
 * returned by `use*` hooks as reactive state that must be serializable, so a
 * hook returning a bound `t()` function would break SSR (Code(3)). Reading the
 * store inside `tr` keeps the call site reactive to language changes.
 */
export const tr = translate;

export function useI18n(): I18nState {
  return useContext(I18nContext);
}

/**
 * Translate an API error code (`pay.err.<code>`), falling back to the generic
 * message. `params` fills placeholders (`amount_too_small` → `{min}`).
 */
export function trError(store: I18nState, code: string | undefined, fallback?: string, params?: Params): string {
  const key = `pay.err.${code ?? ""}` as CatalogKey;
  if (code && key in en) return translate(store, key, params);
  return fallback || translate(store, "pay.err.generic");
}

/** `<prefix>.<value>` when the catalog has it (status / kind labels), else the raw value. */
export function trLabel(store: I18nState, prefix: string, value: string): string {
  const key = `${prefix}.${value}` as CatalogKey;
  return key in en ? translate(store, key) : value;
}
