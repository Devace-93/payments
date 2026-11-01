/**
 * Reference catalog (English), assembled from one file per surface:
 *   en/chrome.ts   nav, footer, controls, building curtain, common words
 *   en/auth.ts     login, signup, magic link, verify, profile, errors
 * Every other language file (`<base>.ts`, optional `<base>-<COUNTRY>.ts`
 * overrides) exports a Partial<Catalog>; missing keys fall back here.
 * Interpolation: `{name}` placeholders are replaced by `tr(i18n, key, { name })`.
 */
import { auth } from "./en/auth";
import { chrome } from "./en/chrome";

const en = { ...chrome, ...auth } as const;

export type CatalogKey = keyof typeof en;
export type Catalog = Record<CatalogKey, string>;
export type PartialCatalog = Partial<Catalog>;
export default en;
