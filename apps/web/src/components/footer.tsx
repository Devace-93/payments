import { component$ } from "@builder.io/qwik";
import { tr, useI18n } from "../i18n";

const GITHUB_URL = "https://github.com/Devace-93/accounts";
const LINKEDIN_URL = "https://www.linkedin.com/in/enrique-magallon/";
const INFO_URL = import.meta.env.VITE_INFO_URL || "https://info.3m4.net";

/**
 * Footer shared in shape with the other 3m4 apps (3m4, kinegram, bubbles,
 * info, metrics, retro, exp): author credit → source → apps index.
 */
export const Footer = component$(() => {
  const i18n = useI18n();
  const year = new Date().getFullYear();
  return (
    <footer class="border-t border-slate-200 bg-slate-50">
      <div class="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-8 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
          <a href={LINKEDIN_URL} target="_blank" rel="noopener noreferrer" class="hover:text-primary-600">
            {tr(i18n, "footer.madeBy")}
          </a>
          <span class="text-slate-300" aria-hidden="true">·</span>
          <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" class="hover:text-primary-600">
            {tr(i18n, "footer.source")}
          </a>
          <span class="text-slate-300" aria-hidden="true">·</span>
          <a href={INFO_URL} class="hover:text-primary-600">
            {INFO_URL.replace(/^https?:\/\//, "")}
          </a>
        </div>
        <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span class="text-slate-400">{tr(i18n, "footer.openSource")} · © {year}</span>
        </div>
      </div>
    </footer>
  );
});
