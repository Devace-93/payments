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
