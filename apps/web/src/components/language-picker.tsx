import { component$, useSignal, useTask$, $ } from "@builder.io/qwik";
import { useLocation } from "@builder.io/qwik-city";
import { LANGS } from "../i18n/langs";
import { setLang, tr, useI18n } from "../i18n";

const norm = (s: string): string => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

/**
 * Language picker shared in spirit with kinegram.3m4.net / bubbles.3m4.net /
 * info.3m4.net: a button with the current flag + name + caret, and a dropdown
 * with a search box over the same 34 country locales.
 */
export const LanguagePicker = component$(() => {
  const i18n = useI18n();
  const loc = useLocation();
  const open = useSignal(false);
  const query = useSignal("");

  // Close on navigation.
  useTask$(({ track }) => {
    track(() => loc.url.pathname);
    open.value = false;
  });

  const pick = $(async (code: string) => {
    await setLang(i18n, code);
    open.value = false;
    query.value = "";
  });

  const current = LANGS.find((l) => l.code === i18n.lang) ?? LANGS.find((l) => l.code === "en-US")!;
  const q = norm(query.value);
  const matches = q ? LANGS.filter((l) => norm(`${l.name} ${l.code} ${l.alias}`).includes(q)) : LANGS;

  return (
    <div class="relative" data-lang-picker>
      <button
        type="button"
        class="btn-ghost h-9 gap-1.5 px-2"
        aria-haspopup="listbox"
        aria-expanded={open.value}
        aria-label={tr(i18n, "ui.language")}
        title={tr(i18n, "ui.language")}
        onClick$={() => {
          open.value = !open.value;
          query.value = "";
        }}
      >
        <span aria-hidden="true">{current.flag}</span>
        <span class="hidden max-w-40 truncate text-sm font-medium lg:inline">{current.name}</span>
        <span class="text-xs opacity-60" aria-hidden="true">
          ▾
        </span>
      </button>

      {open.value && (
        <>
          <button
            type="button"
            class="fixed inset-0 z-40 cursor-default"
            aria-label={tr(i18n, "ui.close")}
            tabIndex={-1}
            onClick$={() => {
              open.value = false;
              query.value = "";
            }}
          />
          <div class="absolute end-0 z-50 mt-1 w-72 rounded-xl border border-slate-200 bg-white p-2 shadow-xl">
            <input
              type="search"
              class="input mb-2"
              placeholder={tr(i18n, "ui.search")}
              aria-label={tr(i18n, "ui.search")}
              autoFocus
              value={query.value}
              onInput$={(_, el) => (query.value = el.value)}
              onKeyDown$={(e) => {
                if (e.key === "Escape") {
                  open.value = false;
                  query.value = "";
                } else if (e.key === "Enter" && matches.length) {
                  pick(matches[0].code);
                }
              }}
            />
            <ul role="listbox" class="max-h-72 overflow-y-auto">
              {matches.map((l) => (
                <li key={l.code}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={l.code === current.code}
                    class={[
                      "flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-start text-sm text-slate-700 hover:bg-slate-100",
                      l.code === current.code ? "bg-primary-50 font-medium text-primary-700" : "",
                    ]}
                    onClick$={() => pick(l.code)}
                  >
                    <span aria-hidden="true">{l.flag}</span>
                    <span class="truncate">{l.name}</span>
                  </button>
                </li>
              ))}
              {matches.length === 0 && <li class="px-2.5 py-2 text-sm text-slate-400">—</li>}
            </ul>
          </div>
        </>
      )}
    </div>
  );
});
