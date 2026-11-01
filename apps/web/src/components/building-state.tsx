import { component$ } from "@builder.io/qwik";
import { tr, useI18n } from "../i18n";

/**
 * Full-page "we're building" curtain, shown when the `site-building` feature
 * is ON (see routes/layout.tsx). The API, the JWKS, the avatars and
 * session.js keep answering — only the hosted pages are curtained.
 */
export const BuildingState = component$(() => {
  const i18n = useI18n();
  return (
    <div class="grid min-h-screen place-items-center bg-slate-50 px-4">
      <div class="text-center">
        <svg
          width="280"
          height="200"
          viewBox="0 0 280 200"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
          class="mx-auto"
        >
          {/* ground */}
          <line x1="20" y1="172" x2="260" y2="172" stroke="#cbd5e1" stroke-width="3" stroke-linecap="round" />
          {/* crane mast */}
          <rect x="60" y="52" width="10" height="120" rx="2" fill="#475569" />
          <path d="M60 172v-120m10 120v-120M60 68l10 12m0-12l-10 12m-10 92h30" stroke="#334155" stroke-width="2" />
          {/* crane jib */}
          <rect x="52" y="44" width="150" height="9" rx="2" fill="#475569" />
          <path d="M70 53l16-9m0 9l16-9m0 9l16-9m0 9l16-9m0 9l16-9m0 9l16-9" stroke="#94a3b8" stroke-width="2" />
          {/* counterweight */}
          <rect x="38" y="53" width="18" height="16" rx="2" fill="#334155" />
          {/* cable + hook */}
          <line x1="186" y1="53" x2="186" y2="96" stroke="#64748b" stroke-width="2" />
          <path d="M186 96c0 5-6 5-6 0" stroke="#64748b" stroke-width="2" fill="none" />
          {/* hanging badge */}
          <g>
            <rect x="148" y="100" width="76" height="34" rx="8" fill="#4f46e5" />
            <circle cx="164" cy="113" r="4" fill="#ffffff" />
            <path d="M157 125c0-4 3.2-6.5 7-6.5s7 2.5 7 6.5" fill="#ffffff" fill-opacity="0.85" />
            <text x="200" y="122" text-anchor="middle" font-family="ui-sans-serif, system-ui" font-size="12" font-weight="700" fill="#ffffff">
              accounts
            </text>
          </g>
          {/* bricks being laid */}
          <g fill="#e2e8f0" stroke="#cbd5e1" stroke-width="1.5">
            <rect x="140" y="156" width="30" height="14" rx="2" />
            <rect x="172" y="156" width="30" height="14" rx="2" />
            <rect x="204" y="156" width="30" height="14" rx="2" />
            <rect x="156" y="141" width="30" height="14" rx="2" />
            <rect x="188" y="141" width="30" height="14" rx="2" />
          </g>
          {/* traffic cone */}
          <g>
            <path d="M104 172l10-26 10 26z" fill="#f59e0b" />
            <rect x="99" y="168" width="30" height="6" rx="3" fill="#d97706" />
            <path d="M109 159h10" stroke="#fff7ed" stroke-width="4" />
          </g>
          {/* sun accent */}
          <circle cx="242" cy="34" r="12" fill="#eef2ff" stroke="#4f46e5" stroke-width="2.5" />
          <circle cx="242" cy="34" r="4" fill="#4f46e5" />
        </svg>

        <h1 class="mt-6 text-3xl font-bold tracking-tight text-slate-900">{tr(i18n, "building.title")}</h1>
        <p class="mx-auto mt-3 max-w-md text-slate-500">{tr(i18n, "building.body")}</p>
        <p class="mt-8 text-xs text-slate-400">{tr(i18n, "building.footer")}</p>
      </div>
    </div>
  );
});
