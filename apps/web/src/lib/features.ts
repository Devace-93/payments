/**
 * accounts' OWN feature switches ("features"), mirrored from the backend (the
 * source of truth). Registry + fail-safe defaults live in
 * `packages/shared/feature_flags.json`. Anonymous pages (login / signup)
 * read them from `GET /api/features`, resolved server-side by the root layout.
 * The UI only hides surfaces — enforcement happens in the Flask API.
 */
import { createContextId } from "@builder.io/qwik";
import registry from "../../../../packages/shared/feature_flags.json";

export type FeatureKey = "site-building" | "signups" | "oauth" | "magic-link";

export type Features = Record<FeatureKey, boolean>;

/** Fail-safe defaults from the shared registry (used until the API answers). */
export const FEATURE_DEFAULTS: Features = Object.fromEntries(
  Object.entries(registry.flags).map(([k, v]) => [k, v.default]),
) as Features;

/** Merge a server-resolved feature map over the defaults. */
export function mergeFeatures(server?: Record<string, boolean>): Features {
  return { ...FEATURE_DEFAULTS, ...(server ?? {}) };
}

/** Provided by the root layout; consume with useContext(FeaturesContext). */
export const FeaturesContext = createContextId<Features>("accounts.features");
