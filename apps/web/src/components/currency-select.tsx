import { component$, type Signal } from "@builder.io/qwik";
import { rememberCurrency } from "../lib/currency";
import { tr, useI18n } from "../i18n";

/**
 * `<select>` over the catalog's currencies. Writing to `value` is enough for
 * the page to react (track the signal); the choice is also persisted in
 * `localStorage["3m4.currency"]` (CONTRACT.md §7).
 */
export const CurrencySelect = component$<{
  id?: string;
  currencies: string[];
  value: Signal<string>;
  disabled?: boolean;
  persist?: boolean;
}>(({ id = "currency", currencies, value, disabled, persist = true }) => {
  const i18n = useI18n();
  return (
    <div>
      <label class="label" for={id}>
        {tr(i18n, "pay.currency")}
      </label>
      <select
        id={id}
        class="input"
        data-testid={id}
        disabled={disabled}
        value={value.value}
        onChange$={(_, el) => {
          value.value = el.value;
          if (persist) rememberCurrency(el.value);
        }}
      >
        {currencies.map((c) => (
          <option key={c} value={c} selected={c === value.value}>
            {c.toUpperCase()}
          </option>
        ))}
      </select>
    </div>
  );
});
