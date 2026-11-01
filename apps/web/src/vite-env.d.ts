/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base of the accounts API (`/api` behind Caddy, absolute in dev). */
  readonly VITE_API_URL?: string;
  /** Public origin of this app (e.g. https://accounts.3m4.net); used to validate return_to. */
  readonly VITE_APP_URL?: string;
  /** Apps index (info.3m4.net); footer link shared by every 3m4 app. */
  readonly VITE_INFO_URL?: string;
  readonly VITE_POSTHOG_KEY?: string;
  readonly VITE_POSTHOG_HOST?: string;
  /** metrics (metrics.3m4.net) project public key; the tracker is rendered only when set. */
  readonly VITE_METRICS_PROJECT_KEY?: string;
  readonly VITE_METRICS_TRACKER_URL?: string;
  /** retro (retro.3m4.net) project public key; the feedback widget is rendered only when set. */
  readonly VITE_RETRO_PROJECT_KEY?: string;
  readonly VITE_RETRO_WIDGET_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
