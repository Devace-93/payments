import { component$, useComputed$, useContext, useSignal, useStore, useTask$, useVisibleTask$, $ } from "@builder.io/qwik";
import { useLocation, type DocumentHead } from "@builder.io/qwik-city";
import { api, ApiRequestError } from "../../../lib/api";
import { formatAmount, fromMinor, resolveCurrency, toMinor } from "../../../lib/currency";
import { FeaturesContext } from "../../../lib/features";
import { readOrigin, readReturnToOrNone } from "../../../lib/returnTo";
import { capture } from "../../../lib/analytics";
import type { Catalog, Me } from "../../../lib/types";
import { CurrencySelect } from "../../../components/currency-select";
import { AppIcon } from "../../../components/app-icon";
import { tr, trError, useI18n } from "../../../i18n";

const MESSAGE_MAX = 200;
const NAME_MAX = 60;

/**
 * `/donate?app=&amount=&currency=&origin=&return_to=&lang=` — the one-time
 * donation form (CONTRACT.md §10). Presets come from the catalog per currency;
 * min/max are the server's values; the fee hint calls GET /api/fees
 * (debounced). "Donate with card" POSTs /api/checkout and follows the URL.
 */
export default component$(() => {
  const loc = useLocation();
  const i18n = useI18n();
  const features = useContext(FeaturesContext);
  const app = loc.url.searchParams.get("app") || "";
  const qAmount = Number(loc.url.searchParams.get("amount") || "") || 0;
  const qCurrency = loc.url.searchParams.get("currency");
  const qLang = loc.url.searchParams.get("lang");

  const catalog = useSignal<Catalog | null>(null);
  const me = useSignal<Me | null>(null);
  const currency = useSignal("usd");
  const amount = useSignal(0); // minor units
  const custom = useSignal(""); // free-text input, whole units
  const form = useStore({ message: "", isPublic: false, displayName: "", loading: true, busy: false, error: "" });
  const fee = useStore({ net: 0, for: 0 });

  // eslint-disable-next-line qwik/no-use-visible-task
  useVisibleTask$(async () => {
    if (!app) {
      form.error = tr(i18n, "pay.unknownApp");
      form.loading = false;
      return;
    }
    try {
      const [cat, user] = await Promise.all([api.getCatalog(app), api.getMe().catch(() => null)]);
      catalog.value = cat;
      me.value = user;
      if (user?.customer.display_name) form.displayName = user.customer.display_name;
      if (user?.customer.public_supporter) form.isPublic = true;
      const cur = await resolveCurrency(cat.currencies, cat.default_currency, user, qCurrency);
      currency.value = cur;
      const presets = cat.donation.presets[cur] ?? [];
      if (qAmount > 0) {
        amount.value = qAmount;
        if (!presets.includes(qAmount)) custom.value = fromMinor(qAmount, cur);
      } else {
        amount.value = presets[1] ?? presets[0] ?? cat.donation.min[cur] ?? 0;
      }
    } catch (e) {
      form.error = e instanceof ApiRequestError ? trError(i18n, e.error.code, e.error.message) : tr(i18n, "pay.err.network");
    } finally {
      form.loading = false;
    }
  });

  // Currency switch: presets change, so snap the amount to the new currency's
  // middle preset unless the user typed a custom value.
  useTask$(({ track }) => {
    const cur = track(() => currency.value);
    const cat = catalog.value;
    if (!cat) return;
    const presets = cat.donation.presets[cur] ?? [];
    if (custom.value) {
      amount.value = toMinor(custom.value, cur) ?? 0;
    } else if (!presets.includes(amount.value)) {
      amount.value = presets[1] ?? presets[0] ?? 0;
    }
  });

  const min = useComputed$(() => catalog.value?.donation.min[currency.value] ?? 0);
  const max = useComputed$(() => catalog.value?.donation.max[currency.value] ?? Number.MAX_SAFE_INTEGER);
  const amountError = useComputed$(() => {
    if (!catalog.value || amount.value <= 0) return "";
    if (amount.value < min.value) return tr(i18n, "pay.minAmount", { min: formatAmount(min.value, currency.value, i18n.lang) });
    if (amount.value > max.value) return tr(i18n, "pay.maxAmount", { max: formatAmount(max.value, currency.value, i18n.lang) });
    return "";
  });
  const sponsorsUrl = useComputed$(() => catalog.value?.github_sponsors_url || import.meta.env.VITE_GITHUB_SPONSORS_URL || "");
  const showFeeHint = useComputed$(() => !!catalog.value?.fee_hint && features["fee-hint"]);

  // Fee hint: debounce GET /api/fees while the amount / currency change.
  useTask$(({ track, cleanup }) => {
    const amt = track(() => amount.value);
    const cur = track(() => currency.value);
    const on = track(() => showFeeHint.value);
    if (!on || amt <= 0 || amt < min.value || amt > max.value) {
      fee.net = 0;
      return;
    }
    const id = setTimeout(async () => {
      try {
        const f = await api.getFees(amt, cur, "donation");
        if (amount.value === amt && currency.value === cur) {
          fee.net = Math.round(f.net_mxn * 100); // API returns MXN major units
          fee.for = amt;
        }
      } catch {
        fee.net = 0;
      }
    }, 300);
    cleanup(() => clearTimeout(id));
  });

  const submit = $(async () => {
    if (!catalog.value || form.busy) return;
    form.error = "";
    if (amount.value <= 0 || amountError.value) {
      form.error = amountError.value || tr(i18n, "pay.err.validation_error");
      return;
    }
    form.busy = true;
    try {
      const res = await api.createCheckout({
        app,
        kind: "donation",
        amount: amount.value,
        currency: currency.value,
        return_to: readReturnToOrNone(loc.url),
        origin: readOrigin(loc.url),
        public: form.isPublic,
        display_name: form.isPublic ? form.displayName.trim() || undefined : undefined,
        message: form.message.trim() || undefined,
        lang: (qLang || i18n.lang).slice(0, 2),
      });
      capture("checkout_started", { app, kind: "donation", currency: currency.value, amount: amount.value });
      location.assign(res.url);
    } catch (e) {
      if (e instanceof ApiRequestError) {
        const serverMin = typeof e.error.min === "number" ? e.error.min : min.value;
        form.error = trError(i18n, e.error.code, e.error.message, { min: formatAmount(serverMin, currency.value, i18n.lang) });
      } else {
        form.error = tr(i18n, "pay.err.network");
      }
      form.busy = false;
    }
  });

  const cat = catalog.value;
  const cur = currency.value;
  const presets = cat?.donation.presets[cur] ?? [];
  const name = cat?.app.name ?? app;
  const disabled = !cat || form.busy || !features.donations;

  return (
    <div class="card p-8">
      <div class="flex items-center gap-3">
        {cat && <AppIcon name={name} icon={cat.app.icon} />}
        <h1 class="text-2xl font-bold text-slate-900">{tr(i18n, "pay.donateTitle", { app: name })}</h1>
      </div>
      <p class="mt-1 text-sm text-slate-500">{tr(i18n, "pay.donateSubtitle")}</p>
      {me.value && (
        <p class="mt-2 text-sm text-primary-700" data-testid="donating-as">
          {tr(i18n, "pay.donatingAs", { handle: me.value.identity.handle })}
        </p>
      )}

      <form class="mt-6 space-y-5" preventdefault:submit onSubmit$={submit}>
        {!features.donations && <div class="alert-warn">{tr(i18n, "pay.err.feature_off")}</div>}
        {form.error && (
          <div class="alert-error" role="alert" aria-live="polite" data-testid="error">
            {form.error}
          </div>
        )}
        {form.loading && <p class="text-sm text-slate-400">{tr(i18n, "common.loading")}</p>}

        <div class="grid gap-4 sm:grid-cols-[1fr_7rem]">
          <fieldset>
            <legend class="label">{tr(i18n, "pay.amount")}</legend>
            <div class="flex flex-wrap gap-2" data-testid="presets">
              {presets.map((amt) => (
                <button
                  key={amt}
                  type="button"
                  class={["btn", amount.value === amt && !custom.value ? "bg-primary-500 text-[#1c1917]" : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"]}
                  aria-pressed={amount.value === amt && !custom.value}
                  data-testid="preset"
                  disabled={disabled}
                  onClick$={() => {
                    custom.value = "";
                    amount.value = amt;
                  }}
                >
                  {formatAmount(amt, cur, i18n.lang)}
                </button>
              ))}
            </div>
          </fieldset>
          {cat && <CurrencySelect currencies={cat.currencies} value={currency} disabled={disabled} />}
        </div>

        <div>
          <label class="label" for="custom-amount">
            {tr(i18n, "pay.customAmount")}
          </label>
          <div class="flex items-center">
            <span class="rounded-s-lg border border-e-0 border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-400">{cur.toUpperCase()}</span>
            <input
              id="custom-amount"
              type="number"
              inputMode="decimal"
              min={cat ? fromMinor(min.value, cur) : undefined}
              max={cat ? fromMinor(max.value, cur) : undefined}
              step="0.01"
              class="input rounded-s-none"
              data-testid="custom-amount"
              disabled={disabled}
              value={custom.value}
              onInput$={(_, el) => {
                custom.value = el.value;
                amount.value = toMinor(el.value, cur) ?? 0;
              }}
            />
          </div>
          {amountError.value && (
            <p class="mt-1 text-xs text-red-700" role="alert" aria-live="polite" data-testid="amount-error">
              {amountError.value}
            </p>
          )}
          {!amountError.value && showFeeHint.value && fee.net > 0 && fee.for === amount.value && (
            <p class="mt-1 text-xs text-slate-500" data-testid="fee-hint">
              {tr(i18n, "pay.feeHint", { net: formatAmount(fee.net, "mxn", i18n.lang) })}
            </p>
          )}
        </div>

        <div>
          <label class="label" for="message">
            {tr(i18n, "pay.message")} <span class="font-normal text-slate-400">{tr(i18n, "common.optional")}</span>
          </label>
          <textarea
            id="message"
            class="input"
            rows={2}
            maxLength={MESSAGE_MAX}
            data-testid="message"
            disabled={disabled}
            value={form.message}
            onInput$={(_, el) => (form.message = el.value)}
          />
          <p class="mt-1 text-xs text-slate-400">
            {tr(i18n, "pay.messageHint")} ({form.message.length}/{MESSAGE_MAX})
          </p>
        </div>

        <div class="space-y-3">
          <label class="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
              data-testid="public"
              disabled={disabled}
              checked={form.isPublic}
              onChange$={(_, el) => (form.isPublic = el.checked)}
            />
            {tr(i18n, "pay.publicToggle")}
          </label>
          {form.isPublic && (
            <div>
              <label class="label" for="display-name">
                {tr(i18n, "pay.displayName")}
              </label>
              <input
                id="display-name"
                type="text"
                class="input"
                maxLength={NAME_MAX}
                autoComplete="nickname"
                data-testid="display-name"
                disabled={disabled}
                value={form.displayName}
                onInput$={(_, el) => (form.displayName = el.value)}
              />
              <p class="mt-1 text-xs text-slate-400">{tr(i18n, "pay.displayNameHint")}</p>
            </div>
          )}
        </div>

        <div class="space-y-2">
          <button type="submit" class="btn-primary w-full" disabled={disabled || !!amountError.value || amount.value <= 0} data-testid="submit">
            {form.busy ? tr(i18n, "pay.donateCardBusy") : tr(i18n, "pay.donateCard")}
          </button>
          {sponsorsUrl.value && (
            <a href={sponsorsUrl.value} target="_blank" rel="noopener noreferrer" class="btn-secondary w-full" data-testid="sponsor-github">
              {tr(i18n, "pay.sponsorGithub")}
            </a>
          )}
        </div>

        {!me.value && !form.loading && (
          <p class="text-xs text-slate-500" data-testid="claim-explainer">
            {tr(i18n, "pay.claimExplainer")}
          </p>
        )}
        <p class="text-xs text-slate-400">{tr(i18n, "pay.securedByStripe")}</p>
      </form>
    </div>
  );
});

export const head: DocumentHead = { title: "Donate — 3m4 payments" };
