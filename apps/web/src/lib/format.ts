/** Small locale-aware formatters shared by the pages. */

export function formatDate(iso: string | null | undefined, lang: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(lang, { dateStyle: "medium" });
  } catch {
    return iso.slice(0, 10);
  }
}

export function formatDateTime(iso: string | null | undefined, lang: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

/**
 * Append a cache-busting `v=` to a URL. The badge SVG is served with
 * `Cache-Control: public, max-age=…`, so a preview rendered right after a
 * donation / claim would otherwise show the stale cached copy. Use it on
 * previews only — never on the copyable snippets.
 */
export function withCacheBust(url: string, rev: number | string): string {
  return `${url}${url.includes("?") ? "&" : "?"}v=${encodeURIComponent(String(rev))}`;
}
