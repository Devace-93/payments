/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base of the payments API (`/api` behind Caddy, absolute in dev). */
  readonly VITE_API_URL?: string;
  /** Public origin of this app (e.g. https://payments.3m4.net); used to validate return_to. */
  readonly VITE_APP_URL?: string;
  /** accounts.3m4.net origin: hosted login/signup pages + session refresh. Default http://localhost:8085. */
  readonly VITE_ACCOUNTS_URL?: string;
  /** GitHub Sponsors profile; shown as a second donate button when set (the catalog's value wins). */
  readonly VITE_GITHUB_SPONSORS_URL?: string;
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
