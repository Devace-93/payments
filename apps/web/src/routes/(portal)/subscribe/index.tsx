import { component$, useContext, useSignal, useStore, useVisibleTask$, $ } from "@builder.io/qwik";
import { Link, useLocation, type DocumentHead } from "@builder.io/qwik-city";
import { api, ApiRequestError, loginUrl } from "../../../lib/api";
import { formatAmount, resolveCurrency } from "../../../lib/currency";
import { FeaturesContext } from "../../../lib/features";
import { readOrigin, readReturnToOrNone } from "../../../lib/returnTo";
import { capture } from "../../../lib/analytics";
import type { Catalog, Me, Product } from "../../../lib/types";
import { CurrencySelect } from "../../../components/currency-select";
import { tr, trError, useI18n } from "../../../i18n";

/**
 * `/subscribe?app=&price=&currency=&origin=&return_to=` — subscriptions need
 * a 3m4 account: no session → hosted login on accounts with `return_to` set
 * to this exact URL (CONTRACT.md §10). Logged in → plan card + currency and
 * "Continue to Stripe" (POST /api/checkout kind=subscription).
 */
export default component$(() => {
  const loc = useLocation();
  const i18n = useI18n();
  const features = useContext(FeaturesContext);
  const app = loc.url.searchParams.get("app") || "";
  const price = loc.url.searchParams.get("price") || "";
  const qCurrency = loc.url.searchParams.get("currency");

  const catalog = useSignal<Catalog | null>(null);
  const me = useSignal<Me | null>(null);
  const product = useSignal<Product | null>(null);
  const currency = useSignal("usd");
  const state = useStore({ loading: true, busy: false, error: "", alreadySubscribed: false, redirecting: false });

  // eslint-disable-next-line qwik/no-use-visible-task
  useVisibleTask$(async () => {
    if (!app || !price) {
      state.error = tr(i18n, app ? "pay.err.unknown_price" : "pay.unknownApp");
      state.loading = false;
      return;
    }
    try {
      const user = await api.getMe();
      if (!user) {
        state.redirecting = true;
        location.assign(loginUrl(location.href));
        return;
      }
      me.value = user;
      const cat = await api.getCatalog(app);
      catalog.value = cat;
      const p = cat.products.find((x) => x.key === price) ?? null;
      product.value = p;
      if (!p) state.error = tr(i18n, "pay.err.unknown_price");
      currency.value = await resolveCurrency(cat.currencies, cat.default_currency, user, qCurrency);
    } catch (e) {
      state.error = e instanceof ApiRequestError ? trError(i18n, e.error.code, e.error.message) : tr(i18n, "pay.err.network");
    } finally {
      state.loading = false;
    }
  });

  const submit = $(async () => {
    if (!product.value || state.busy) return;
    state.error = "";
    state.alreadySubscribed = false;
    state.busy = true;
    try {
      const res = await api.createCheckout({
        app,
        kind: "subscription",
        price,
        currency: currency.value,
        return_to: readReturnToOrNone(loc.url),
        origin: readOrigin(loc.url),
        lang: i18n.lang.slice(0, 2),
      });
      capture("checkout_started", { app, kind: "subscription", price, currency: currency.value });
      location.assign(res.url);
    } catch (e) {
      if (e instanceof ApiRequestError) {
        if (e.status === 401) {
          location.assign(loginUrl(location.href));
          return;
        }
        state.alreadySubscribed = e.error.code === "already_subscribed";
        state.error = trError(i18n, e.error.code, e.error.message);
      } else {
        state.error = tr(i18n, "pay.err.network");
      }
      state.busy = false;
    }
  });

  const cat = catalog.value;
  const p = product.value;
  const cur = currency.value;
  const name = cat?.app.name ?? app;
  const disabled = !p || state.busy || !features.subscriptions;

  if (state.redirecting) {
    return (
      <div class="card p-8 text-center">
        <p class="text-sm text-slate-500" data-testid="login-redirect">
          {tr(i18n, "pay.loginRequired")}
        </p>
        <a href={loginUrl()} class="btn-primary mt-4">
          {tr(i18n, "pay.logIn")}
        </a>
      </div>
    );
  }

  return (
    <div class="card p-8">
      <h1 class="text-2xl font-bold text-slate-900">{tr(i18n, "pay.subscribeTitle", { app: name })}</h1>
      <p class="mt-1 text-sm text-slate-500">{tr(i18n, "pay.subscribeSubtitle")}</p>
      {me.value && (
        <p class="mt-2 text-sm text-primary-700" data-testid="subscribing-as">
          {tr(i18n, "pay.subscribingAs", { handle: me.value.identity.handle })}
        </p>
      )}

      <form class="mt-6 space-y-5" preventdefault:submit onSubmit$={submit}>
        {!features.subscriptions && <div class="alert-warn">{tr(i18n, "pay.err.feature_off")}</div>}
        {state.error && (
          <div class="alert-error" role="alert" aria-live="polite" data-testid="error">
            {state.error}
            {state.alreadySubscribed && (
              <>
                {" "}
                <Link href="/me?portal=1" class="font-medium underline">
                  {tr(i18n, "pay.alreadySubscribedCta")}
                </Link>
              </>
            )}
          </div>
        )}
        {state.loading && <p class="text-sm text-slate-400">{tr(i18n, "common.loading")}</p>}

        {p && cat && (
          <div class="rounded-xl border border-primary-200 bg-primary-50 p-5" data-testid="plan-card">
            <div class="text-xs font-semibold uppercase tracking-wide text-primary-700">{tr(i18n, "pay.plan")}</div>
            <div class="mt-1 text-lg font-semibold text-slate-900">{p.label}</div>
            <div class="text-sm text-slate-600">
              <span class="text-xl font-bold text-slate-900" data-testid="plan-amount">
                {formatAmount(p.amounts[cur] ?? p.amounts[cat.default_currency], cur, i18n.lang)}
              </span>{" "}
              {tr(i18n, p.interval === "year" ? "pay.perYear" : "pay.perMonth")}
            </div>
            <div class="mt-1 text-xs text-slate-500">{name}</div>
          </div>
        )}

        {cat && <CurrencySelect currencies={cat.currencies} value={currency} disabled={disabled} />}

        <button type="submit" class="btn-primary w-full" disabled={disabled} data-testid="submit">
          {state.busy ? tr(i18n, "pay.donateCardBusy") : tr(i18n, "pay.continueStripe")}
        </button>
        <p class="text-xs text-slate-400">{tr(i18n, "pay.securedByStripe")}</p>
      </form>
    </div>
  );
});

export const head: DocumentHead = { title: "Subscribe — 3m4 payments" };
