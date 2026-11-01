import { component$, Slot, useContextProvider, useStore, useTask$, useVisibleTask$ } from "@builder.io/qwik";
import { routeLoader$ } from "@builder.io/qwik-city";
import { initAnalytics } from "../lib/analytics";
import { BuildingState } from "../components/building-state";
import { I18nContext, initI18n, type I18nState } from "../i18n";
import { DEFAULT_LANG } from "../i18n/langs";
import { FeaturesContext, type Features } from "../lib/features";
import { fetchServerFeatures } from "../lib/features.server";

/**
 * Root layout — resolves accounts' public features on the server for every
 * route (signups / oauth / magic-link switches), initializes PostHog once, and
 * enforces the `site-building` curtain: while that feature is ON every page
 * renders the building page instead of the app (the API, the JWKS, the
 * avatars and session.js are unaffected).
 *
 * Resolving on the server means the SSR HTML already reflects the features,
 * so neither the real site nor a gated section flashes. On any error the
 * loader falls back to the registry defaults — feature resolution must never
 * be able to take the login pages down by accident.
 */
export const useServerFeatures = routeLoader$<Features>(() => fetchServerFeatures());

export default component$(() => {
  const serverFeatures = useServerFeatures();
  const features = useStore<Features>({ ...serverFeatures.value });
  useContextProvider(FeaturesContext, features);
  const i18n = useStore<I18nState>({ lang: DEFAULT_LANG, strings: {} });
  useContextProvider(I18nContext, i18n);

  // Resolve the viewer's locale and load its catalog (SSR renders English).
  // eslint-disable-next-line qwik/no-use-visible-task
  useVisibleTask$(() => {
    initI18n(i18n);
  });

  // Keep the store in sync when the loader re-runs on client-side navigation.
  useTask$(({ track }) => {
    Object.assign(features, track(() => serverFeatures.value));
  });

  // eslint-disable-next-line qwik/no-use-visible-task
  useVisibleTask$(() => {
    initAnalytics();
  });

  return features["site-building"] ? <BuildingState /> : <Slot />;
});
