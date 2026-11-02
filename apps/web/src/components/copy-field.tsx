import { component$, useSignal, $ } from "@builder.io/qwik";
import { tr, useI18n } from "../i18n";

/** Read-only text with a Copy button (badge snippets). */
export const CopyField = component$<{ id: string; label: string; value: string }>(({ id, label, value }) => {
  const i18n = useI18n();
  const copied = useSignal(false);
  const copy = $(async () => {
    try {
      await navigator.clipboard.writeText(value);
      copied.value = true;
      setTimeout(() => (copied.value = false), 1500);
    } catch {
      const el = document.getElementById(id) as HTMLInputElement | null;
      el?.select();
    }
  });
  return (
    <div>
      <label class="label" for={id}>
        {label}
      </label>
      <div class="flex gap-2">
        <input id={id} type="text" class="input font-mono text-xs" readOnly value={value} data-testid={id} onFocus$={(_, el) => el.select()} />
        <button type="button" class="btn-secondary shrink-0" onClick$={copy} aria-live="polite">
          {copied.value ? tr(i18n, "common.copied") : tr(i18n, "common.copy")}
        </button>
      </div>
    </div>
  );
});
