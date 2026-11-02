/**
 * Reference catalog (English), assembled from one file per surface:
 *   en/chrome.ts   nav, footer, controls, building curtain, common words
 *   en/pay.ts      home, donate, subscribe, success, cancel, claim, me, errors
 * Every other language file (`<base>.ts`, optional `<base>-<COUNTRY>.ts`
 * overrides) exports a Partial<Catalog>; missing keys fall back here.
 * Interpolation: `{name}` placeholders are replaced by `tr(i18n, key, { name })`.
 * (pay.js has its own en/es strings in packages/pay-js.)
 */
import { chrome } from "./en/chrome";
import { pay } from "./en/pay";

const en = { ...chrome, ...pay } as const;

export type CatalogKey = keyof typeof en;
export type Catalog = Record<CatalogKey, string>;
export type PartialCatalog = Partial<Catalog>;
export default en;
