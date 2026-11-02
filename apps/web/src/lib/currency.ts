/**
 * Currency resolution and formatting (CONTRACT.md §7).
 *
 * Order: 1. `me.customer.preferred_currency` (JWT claim mirrored by the API),
 * 2. `localStorage["3m4.currency"]`, 3. the country of `localStorage["3m4.lang"]`
 * (es-MX → mxn, en-US → usd, EU locales → eur, else usd), 4. `GET /api/geo`,
 * 5. the catalog's `default_currency`. The user can always change it; the
 * choice is stored in `3m4.currency`.
 */
import { api } from "./api";
import { LANG_STORAGE_KEY } from "../i18n/langs";
import type { Currency, Me } from "./types";

export const CURRENCY_STORAGE_KEY = "3m4.currency";

/** Locale → currency for the 34 locales in i18n/langs.ts (EU members → eur). */
export const LOCALE_CURRENCY: Record<string, Currency> = {
  "es-MX": "mxn",
  "es-ES": "eur",
  "es-CO": "usd",
  "es-AR": "usd",
  "es-CL": "usd",
  "es-PE": "usd",
  "en-US": "usd",
  "en-GB": "eur",
  "en-CA": "usd",
  "en-AU": "usd",
  "en-NZ": "usd",
  "fr-FR": "eur",
  "de-DE": "eur",
  "de-AT": "eur",
  "it-IT": "eur",
  "pt-BR": "usd",
  "pt-PT": "eur",
  "nl-NL": "eur",
  "sv-SE": "eur",
  "pl-PL": "eur",
  "cs-CZ": "eur",
  "ro-RO": "eur",
  "el-GR": "eur",
  "uk-UA": "eur",
  "ru-RU": "usd",
  "tr-TR": "eur",
  "ar-SA": "usd",
  "hi-IN": "usd",
  "zh-CN": "usd",
  "ja-JP": "usd",
  "ko-KR": "usd",
  "vi-VN": "usd",
  "id-ID": "usd",
  "th-TH": "usd",
};

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function currencyForLang(lang: string | null | undefined): Currency | null {
  if (!lang) return null;
  if (LOCALE_CURRENCY[lang]) return LOCALE_CURRENCY[lang];
  const base = lang.slice(0, 2);
  const hit = Object.entries(LOCALE_CURRENCY).find(([code]) => code.startsWith(base));
  return hit ? hit[1] : null;
}

/** Remember the user's explicit choice (§7: "stored in 3m4.currency"). */
export function rememberCurrency(currency: Currency): void {
  try {
    localStorage.setItem(CURRENCY_STORAGE_KEY, currency);
  } catch {
    /* ignore */
  }
}

/**
 * Resolve the currency to preselect. `allowed` is the catalog's `currencies`;
 * a candidate outside it is skipped. `me` may be `null` (guest) or `undefined`
 * (not fetched). Steps 1–3 are synchronous; 4 hits `/api/geo` only when needed.
 */
export async function resolveCurrency(
  allowed: Currency[],
  fallback: Currency,
  me?: Me | null,
  hint?: string | null,
): Promise<Currency> {
  const ok = (c: string | null | undefined): c is Currency => !!c && allowed.includes(c.toLowerCase());
  const norm = (c: string) => c.toLowerCase();
  if (ok(hint)) return norm(hint);
  if (ok(me?.customer?.preferred_currency)) return norm(me!.customer.preferred_currency!);
  const saved = read(CURRENCY_STORAGE_KEY);
  if (ok(saved)) return norm(saved);
  const byLang = currencyForLang(read(LANG_STORAGE_KEY) || (typeof navigator !== "undefined" ? navigator.language : null));
  if (ok(byLang)) return byLang;
  try {
    const geo = await api.getGeo();
    if (ok(geo.currency)) return norm(geo.currency);
  } catch {
    /* geo never blocks */
  }
  return ok(fallback) ? norm(fallback) : allowed[0] || "usd";
}

/** Currencies whose minor unit is not 1/100 (none of ours today, kept for safety). */
const ZERO_DECIMAL = new Set(["jpy", "krw", "vnd", "clp", "isk", "huf", "twd", "ugx"]);

export function minorUnits(currency: Currency): number {
  return ZERO_DECIMAL.has(currency.toLowerCase()) ? 1 : 100;
}

/** `formatAmount(500, "usd", "en-US")` → "$5.00"; falls back to "5.00 USD". */
export function formatAmount(cents: number, currency: Currency, locale = "en-US"): string {
  const value = cents / minorUnits(currency);
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currency.toUpperCase(),
      currencyDisplay: "narrowSymbol",
    }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency.toUpperCase()}`;
  }
}

/** Whole-unit input value → minor units (rounds to the cent). */
export function toMinor(value: string | number, currency: Currency): number | null {
  const n = typeof value === "number" ? value : Number(String(value).replace(",", "."));
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n * minorUnits(currency));
}

/** Minor units → input value string ("5", "5.5"). */
export function fromMinor(cents: number, currency: Currency): string {
  const v = cents / minorUnits(currency);
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}
