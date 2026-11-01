import { component$, useSignal, useVisibleTask$, $ } from "@builder.io/qwik";
import { getTheme, setTheme, type Theme } from "../lib/theme";
import { tr, useI18n } from "../i18n";

/** ☀️ / 🌙 toggle, mirroring the other 3m4 apps. */
export const ThemeToggle = component$(() => {
  const i18n = useI18n();
  // null until hydrated: the server does not know the viewer's preference.
  const theme = useSignal<Theme | null>(null);

  // eslint-disable-next-line qwik/no-use-visible-task
  useVisibleTask$(() => {
    theme.value = getTheme();
  });

  const toggle = $(() => {
    const next: Theme = (theme.value ?? getTheme()) === "light" ? "dark" : "light";
    setTheme(next);
    theme.value = next;
  });

  const label = theme.value === "dark" ? tr(i18n, "ui.themeLight") : tr(i18n, "ui.themeDark");
  return (
    <button
      type="button"
      class="btn-ghost h-9 w-9 px-0 text-base"
      aria-label={label}
      title={label}
      data-theme-toggle
      onClick$={toggle}
    >
      {theme.value === null ? <span class="opacity-0">🌙</span> : theme.value === "light" ? "🌙" : "☀️"}
    </button>
  );
});
