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
 *   3m4 apps so the choice carries across them.
 */
import { createContextId, useContext } from "@builder.io/qwik";
import en, { type CatalogKey, type PartialCatalog } from "./catalog/en";
import { baseOf, DEFAULT_LANG, isRtl, LANG_STORAGE_KEY, resolveLang } from "./langs";

export interface I18nState {
  lang: string;
  /** Merged strings for the active locale (base + country overrides). */
  strings: PartialCatalog;
}

export const I18nContext = createContextId<I18nState>("accounts.i18n");

// One chunk per catalog file; Vite resolves the glob at build time.
const loaders = import.meta.glob<{ default: PartialCatalog }>("./catalog/*.ts");

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

/** Resolve the locale on the client and load its catalog into the store. */
export async function initI18n(store: I18nState): Promise<void> {
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
 *   <h1>{tr(i18n, "auth.loginTitle")}</h1>
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

/** Translate an API error code (`auth.err.<code>`), falling back to the generic message. */
export function trError(store: I18nState, code: string | undefined, fallback?: string): string {
  const key = `auth.err.${code ?? ""}` as CatalogKey;
  if (code && key in en) return translate(store, key);
  return fallback || translate(store, "auth.err.generic");
}
