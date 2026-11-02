import { component$, useContext, useSignal, useStore, useVisibleTask$ } from "@builder.io/qwik";
import { Link, routeLoader$, useLocation, type DocumentHead } from "@builder.io/qwik-city";
import { api, ApiRequestError } from "../../lib/api";
import { formatAmount, resolveCurrency } from "../../lib/currency";
import { FeaturesContext } from "../../lib/features";
import type { Catalog } from "../../lib/types";
import { CurrencySelect } from "../../components/currency-select";
import { tr, trError, useI18n } from "../../i18n";

/**
 * `/` — with `?app=` the app's catalog (donation presets + plans), without it
 * a picker over the known apps. The `3m4_session` cookie is only a hint (the
 * API verifies it); it lets us feature the "Your support" link on the server.
 */
export const useSessionHint = routeLoader$(({ cookie }) => cookie.has("3m4_session"));

/** Mirrors packages/shared/catalog.json (slugs the API knows). */
const KNOWN_APPS: { slug: string; name: string; url: string }[] = [
  { slug: "3m4", name: "3m4", url: "https://3m4.net" },
  { slug: "info", name: "3m4 info", url: "https://info.3m4.net" },
  { slug: "mousetouch", name: "MouseTouch", url: "https://mouse.3m4.net" },
  { slug: "retro", name: "Retro", url: "https://retro.3m4.net" },
];

export default component$(() => {
  const loc = useLocation();
  const i18n = useI18n();
  const features = useContext(FeaturesContext);
  const hasSession = useSessionHint();
  const app = loc.url.searchParams.get("app") || "";

  const catalog = useSignal<Catalog | null>(null);
  const currency = useSignal("usd");
  const state = useStore({ error: "", loading: !!app });

  // eslint-disable-next-line qwik/no-use-visible-task
  useVisibleTask$(async () => {
    if (!app) return;
    try {
      const [cat, me] = await Promise.all([api.getCatalog(app), api.getMe().catch(() => null)]);
      catalog.value = cat;
      currency.value = await resolveCurrency(cat.currencies, cat.default_currency, me);
    } catch (e) {
      state.error = e instanceof ApiRequestError ? trError(i18n, e.error.code, e.error.message) : tr(i18n, "pay.err.network");
    } finally {
      state.loading = false;
    }
  });


  if (!app) {
    return (
      <div class="space-y-6">
        <header class="text-center">
          <h1 class="text-3xl font-bold tracking-tight text-slate-900">{tr(i18n, "pay.homeTitle")}</h1>
          <p class="mx-auto mt-2 max-w-lg text-sm text-slate-500">{tr(i18n, "pay.homeSubtitle")}</p>
        </header>

        {hasSession.value && (
          <Link href="/me" class="card flex items-center justify-between gap-3 border-sky-200 bg-sky-50 p-5 hover:border-sky-400" data-testid="me-link">
            <div>
              <div class="font-semibold text-slate-900">{tr(i18n, "pay.yourSupport")}</div>
              <div class="text-sm text-slate-500">{tr(i18n, "pay.yourSupportHint")}</div>
            </div>
            <span aria-hidden="true" class="text-sky-700">
              →
            </span>
          </Link>
        )}

        <section>
          <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{tr(i18n, "pay.pickApp")}</h2>
          <ul class="grid gap-3 sm:grid-cols-2" data-testid="app-picker">
            {KNOWN_APPS.map((a) => (
              <li key={a.slug}>
                <Link href={`/?app=${a.slug}`} class="card block p-5 hover:border-primary-400">
                  <div class="font-semibold text-slate-900">{a.name}</div>
                  <div class="text-xs text-slate-400">{a.url.replace(/^https?:\/\//, "")}</div>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        {!hasSession.value && (
          <p class="text-center text-sm text-slate-500">
            <Link href="/me" class="font-medium text-primary-700 hover:underline">
              {tr(i18n, "pay.yourSupport")}
            </Link>
          </p>
        )}
      </div>
    );
  }

  const cat = catalog.value;
  const cur = currency.value;
  const presets = cat?.donation.presets[cur] ?? [];
  const name = cat?.app.name ?? KNOWN_APPS.find((a) => a.slug === app)?.name ?? app;
  const qs = (extra: Record<string, string>) => {
    const p = new URLSearchParams({ app, currency: cur, ...extra });
    for (const k of ["return_to", "origin"]) {
      const v = loc.url.searchParams.get(k);
      if (v) p.set(k, v);
    }
    return `?${p}`;
  };

  return (
    <div class="space-y-6">
      <header class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p class="text-sm text-slate-500">
            <Link href="/" class="hover:underline">
              {tr(i18n, "nav.home")}
            </Link>{" "}
            / {name}
          </p>
          <h1 class="text-3xl font-bold tracking-tight text-slate-900">{tr(i18n, "pay.donateTitle", { app: name })}</h1>
        </div>
        {cat && (
          <div class="w-28">
            <CurrencySelect currencies={cat.currencies} value={currency} />
          </div>
        )}
      </header>

      {state.error && (
        <div class="alert-error" role="alert" data-testid="error">
          {state.error}
        </div>
      )}
      {state.loading && <p class="text-sm text-slate-400">{tr(i18n, "common.loading")}</p>}

      {cat && features.donations && (
        <section class="card p-6" data-testid="catalog-donate">
          <h2 class="text-lg font-semibold text-slate-900">{tr(i18n, "pay.catalogDonate")}</h2>
          <p class="mt-1 text-sm text-slate-500">{tr(i18n, "pay.catalogDonateBody", { app: name })}</p>
          <div class="mt-4 flex flex-wrap gap-2">
            {presets.map((amt) => (
              <Link key={amt} href={`/donate${qs({ amount: String(amt) })}`} class="btn-secondary" data-testid="preset">
                {formatAmount(amt, cur, i18n.lang)}
              </Link>
            ))}
            <Link href={`/donate${qs({})}`} class="btn-primary">
              {tr(i18n, "pay.customAmount")}
            </Link>
          </div>
        </section>
      )}

      {cat && (
        <section class="card p-6" data-testid="catalog-plans">
          <h2 class="text-lg font-semibold text-slate-900">{tr(i18n, "pay.catalogPlans")}</h2>
          {cat.products.length === 0 ? (
            <p class="mt-1 text-sm text-slate-500">{tr(i18n, "pay.noProducts", { app: name })}</p>
          ) : (
            <ul class="mt-4 divide-y divide-slate-200">
              {cat.products.map((p) => (
                <li key={p.key} class="flex flex-wrap items-center justify-between gap-3 py-3" data-testid={`plan-${p.key}`}>
                  <div>
                    <div class="font-medium text-slate-900">{p.label}</div>
                    <div class="text-sm text-slate-500">
                      {formatAmount(p.amounts[cur] ?? p.amounts[cat.default_currency], cur, i18n.lang)}{" "}
                      {tr(i18n, p.interval === "year" ? "pay.perYear" : "pay.perMonth")}
                    </div>
                  </div>
                  {features.subscriptions ? (
                    <Link href={`/subscribe${qs({ price: p.key })}`} class="btn-primary">
                      {tr(i18n, "pay.catalogSubscribe")}
                    </Link>
                  ) : (
                    <span class="badge bg-slate-100 text-slate-500">{tr(i18n, "pay.err.feature_off")}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
});

export const head: DocumentHead = { title: "3m4 payments — support every 3m4 app" };
