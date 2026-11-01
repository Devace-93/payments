/**
 * Server-side feature resolution (SSR only — imported from routeLoader$).
 *
 * The root layout resolves the public features while rendering so the first
 * paint already shows the right surfaces (no blank page, no gated-section
 * flash, and crawlers see real content). The API is reached directly over the
 * internal network via `API_INTERNAL_URL` (compose: http://api:5000/api); when
 * that is unset we fall back to an absolute `VITE_API_URL`, and when neither
 * is usable — or the API is slow/down — we return the registry defaults so
 * feature resolution can never take the site down.
 */
import { FEATURE_DEFAULTS, mergeFeatures, type Features } from "./features";

const TIMEOUT_MS = 1500;
const CACHE_TTL_MS = 15_000;

let cached: { features: Features; at: number } | null = null;

function apiBase(): string | null {
  const internal = process.env.API_INTERNAL_URL;
  if (internal) return internal.replace(/\/$/, "");
  const pub = import.meta.env.VITE_API_URL || "";
  if (/^https?:\/\//.test(pub)) return pub.replace(/\/$/, "");
  return null;
}

export async function fetchServerFeatures(): Promise<Features> {
  if (cached && Date.now() - cached.at < CACHE_TTL_MS) return cached.features;
  const base = apiBase();
  if (!base) return { ...FEATURE_DEFAULTS };
  try {
    const res = await fetch(`${base}/features`, {
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) throw new Error(`features ${res.status}`);
    const data = (await res.json()) as { features?: Record<string, boolean> };
    const features = mergeFeatures(data.features);
    cached = { features, at: Date.now() };
    return features;
  } catch {
    return cached?.features ?? { ...FEATURE_DEFAULTS };
  }
}
