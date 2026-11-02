import { component$, useContext, useSignal, useStore, useVisibleTask$, $ } from "@builder.io/qwik";
import { Link, useLocation, type DocumentHead } from "@builder.io/qwik-city";
import { api, ApiRequestError, loginUrl } from "../../../lib/api";
import { formatAmount, rememberCurrency } from "../../../lib/currency";
import { formatDate } from "../../../lib/format";
import { FeaturesContext } from "../../../lib/features";
import type { Me } from "../../../lib/types";
import { CopyField } from "../../../components/copy-field";
import { tr, trError, trLabel, useI18n, type I18nState } from "../../../i18n";

const NAME_MAX = 60;
const FALLBACK_CURRENCIES = ["usd", "mxn", "eur"];

function errorText(i18n: I18nState, e: unknown): string {
  return e instanceof ApiRequestError ? trError(i18n, e.error.code, e.error.message) : tr(i18n, "pay.err.network");
}

/**
 * `/me` — the support page: subscriptions (Manage → Stripe Customer Portal),
 * payment history, public-supporter toggle + display name, preferred
 * currency, supporter badge snippets. Login gate via accounts; `?portal=1`
 * opens the portal straight away (apps deep-link `/me?app=retro&portal=1`).
 */
export default component$(() => {
  const loc = useLocation();
  const i18n = useI18n();
  const features = useContext(FeaturesContext);

  const me = useSignal<Me | null>(null);
  const currencies = useSignal<string[]>(FALLBACK_CURRENCIES);
  const loadError = useSignal("");
  const portal = useStore({ busy: false, error: "" });
  const pub = useStore({ on: false, name: "", saving: false, msg: "", error: "" });
  const cur = useStore({ value: "", saving: false, msg: "", error: "" });

  const openPortal = $(async () => {
    if (portal.busy) return;
    portal.error = "";
    portal.busy = true;
    try {
      const res = await api.createPortal(`${location.origin}/me`);
      location.assign(res.url);
    } catch (e) {
      portal.error = errorText(i18n, e);
      portal.busy = false;
    }
  });

  const load = $(async () => {
    loadError.value = "";
    try {
      const data = await api.getMe();
      if (!data) {
        location.assign(loginUrl(location.href));
        return;
      }
      me.value = data;
      pub.on = data.customer.public_supporter;
      pub.name = data.customer.display_name ?? data.identity.name ?? data.identity.handle;
      cur.value = data.customer.preferred_currency ?? "";
      api
        .getCatalog("3m4")
        .then((c) => (currencies.value = c.currencies))
        .catch(() => undefined);
      if (loc.url.searchParams.get("portal") === "1") openPortal();
    } catch (e) {
      loadError.value = errorText(i18n, e);
    }
  });

  // eslint-disable-next-line qwik/no-use-visible-task
  useVisibleTask$(() => {
    load();
  });

  const savePublic = $(async () => {
    if (!me.value) return;
    pub.error = "";
    pub.msg = "";
    pub.saving = true;
    try {
      const res = await api.patchMe({ public_supporter: pub.on, display_name: pub.on ? pub.name.trim() || null : undefined });
      me.value = { ...me.value, customer: res.customer };
      pub.msg = tr(i18n, "common.saved");
    } catch (e) {
      pub.error = errorText(i18n, e);
    } finally {
      pub.saving = false;
    }
  });

  const saveCurrency = $(async () => {
    if (!me.value) return;
    cur.error = "";
    cur.msg = "";
    cur.saving = true;
    try {
      const res = await api.patchMe({ preferred_currency: cur.value || null });
      me.value = { ...me.value, customer: res.customer };
      if (cur.value) rememberCurrency(cur.value);
      cur.msg = tr(i18n, "common.saved");
    } catch (e) {
      cur.error = errorText(i18n, e);
    } finally {
      cur.saving = false;
    }
  });

  if (loadError.value) {
    return (
      <div class="card p-8 text-center">
        <p class="text-sm text-red-700" role="alert" data-testid="error">
          {loadError.value}
        </p>
        <button type="button" class="btn-secondary mt-4" onClick$={load}>
          {tr(i18n, "common.retry")}
        </button>
      </div>
    );
  }

  const data = me.value;
  if (!data) {
    return (
      <div class="card p-8 text-center">
        <p class="text-sm text-slate-400">{tr(i18n, "common.loading")}</p>
      </div>
    );
  }

  return (
    <div class="space-y-6">
      <header>
        <h1 class="text-2xl font-bold text-slate-900">{tr(i18n, "pay.meTitle")}</h1>
        <p class="mt-1 text-sm text-slate-500" data-testid="me-handle">
          {tr(i18n, "pay.meSubtitle", { handle: data.identity.handle })}
        </p>
      </header>

      {/* ── Subscriptions ────────────────────────────────────────────────── */}
      <section class="card p-6" data-testid="subscriptions">
        <h2 class="text-lg font-semibold text-slate-900">{tr(i18n, "pay.subscriptions")}</h2>
        {portal.error && (
          <div class="alert-error mt-3" role="alert" data-testid="error">
            {portal.error}
          </div>
        )}
        {portal.busy && <p class="mt-3 text-sm text-slate-400">{tr(i18n, "pay.openingPortal")}</p>}
        {data.subscriptions.length === 0 ? (
          <p class="mt-1 text-sm text-slate-500">{tr(i18n, "pay.noSubscriptions")}</p>
        ) : (
          <ul class="mt-4 divide-y divide-slate-200">
            {data.subscriptions.map((s) => (
              <li key={s.id} class="flex flex-wrap items-center justify-between gap-3 py-3" data-testid="subscription-row">
                <div>
                  <div class="flex items-center gap-2 text-sm font-medium text-slate-900">
                    <span>
                      {s.app} · {s.label}
                    </span>
                    <span class={["badge", s.status === "active" || s.status === "trialing" ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800"]}>
                      {trLabel(i18n, "pay.status", s.status)}
                    </span>
                  </div>
                  {s.current_period_end && (
                    <div class="text-xs text-slate-400">
                      {tr(i18n, s.cancel_at_period_end ? "pay.endsOn" : "pay.renews", { date: formatDate(s.current_period_end, i18n.lang) })}
                    </div>
                  )}
                </div>
                <button type="button" class="btn-secondary" disabled={portal.busy} onClick$={openPortal} data-testid="manage">
                  {tr(i18n, "pay.manage")}
                </button>
              </li>
            ))}
          </ul>
        )}
        {data.subscriptions.length === 0 && data.customer.has_stripe_customer && (
          <button type="button" class="btn-ghost mt-3" disabled={portal.busy} onClick$={openPortal} data-testid="manage">
            {tr(i18n, "pay.manage")}
          </button>
        )}
      </section>

      {/* ── Payments ─────────────────────────────────────────────────────── */}
      <section class="card p-6" data-testid="payments">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2 class="text-lg font-semibold text-slate-900">{tr(i18n, "pay.payments")}</h2>
          <Link href="/claim" class="btn-ghost" data-testid="claim-another">
            {tr(i18n, "pay.claimAnother")}
          </Link>
        </div>
        {data.payments.length === 0 ? (
          <p class="mt-1 text-sm text-slate-500">{tr(i18n, "pay.noPayments")}</p>
        ) : (
          <ul class="mt-4 divide-y divide-slate-200">
            {data.payments.map((p) => (
              <li key={p.id} class="flex flex-wrap items-center justify-between gap-3 py-3 text-sm" data-testid="payment-row">
                <div>
                  <div class="font-medium text-slate-900">
                    {formatAmount(p.amount, p.currency, i18n.lang)} · {p.app}
                  </div>
                  <div class="text-xs text-slate-400">
                    {formatDate(p.created_at, i18n.lang)} · {trLabel(i18n, "pay.kind", p.kind)}
                    {p.message ? ` · “${p.message}”` : ""}
                  </div>
                </div>
                <span class={["badge", p.status === "succeeded" ? "bg-green-100 text-green-800" : p.status === "pending" ? "bg-slate-100 text-slate-600" : "bg-red-100 text-red-800"]}>
                  {trLabel(i18n, "pay.pstatus", p.status)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── Public supporter ─────────────────────────────────────────────── */}
      <section class="card p-6" data-testid="public-supporter">
        <h2 class="text-lg font-semibold text-slate-900">{tr(i18n, "pay.publicSupporter")}</h2>
        <p class="mt-1 text-sm text-slate-500">{tr(i18n, "pay.publicSupporterBody")}</p>
        <form class="mt-4 space-y-4" preventdefault:submit onSubmit$={savePublic}>
          {pub.error && (
            <div class="alert-error" role="alert" data-testid="error">
              {pub.error}
            </div>
          )}
          {pub.msg && (
            <div class="alert-ok" aria-live="polite">
              {pub.msg}
            </div>
          )}
          <label class="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
              data-testid="public-toggle"
              checked={pub.on}
              onChange$={(_, el) => (pub.on = el.checked)}
            />
            {tr(i18n, "pay.publicToggle")}
          </label>
          {pub.on && (
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
                value={pub.name}
                onInput$={(_, el) => (pub.name = el.value)}
              />
              <p class="mt-1 text-xs text-slate-400">{tr(i18n, "pay.displayNameHint")}</p>
            </div>
          )}
          <button type="submit" class="btn-primary" disabled={pub.saving} data-testid="save-public">
            {pub.saving ? tr(i18n, "common.saving") : tr(i18n, "common.save")}
          </button>
        </form>
      </section>

      {/* ── Preferred currency ───────────────────────────────────────────── */}
      <section class="card p-6" data-testid="preferred-currency">
        <h2 class="text-lg font-semibold text-slate-900">{tr(i18n, "pay.preferredCurrency")}</h2>
        <p class="mt-1 text-sm text-slate-500">{tr(i18n, "pay.preferredCurrencyBody")}</p>
        <form class="mt-4 flex flex-wrap items-end gap-3" preventdefault:submit onSubmit$={saveCurrency}>
          <div class="w-40">
            <label class="label" for="preferred-currency">
              {tr(i18n, "pay.currency")}
            </label>
            <select id="preferred-currency" class="input" data-testid="preferred-currency-select" value={cur.value} onChange$={(_, el) => (cur.value = el.value)}>
              <option value="" selected={cur.value === ""}>
                —
              </option>
              {currencies.value.map((c) => (
                <option key={c} value={c} selected={c === cur.value}>
                  {c.toUpperCase()}
                </option>
              ))}
            </select>
          </div>
          <button type="submit" class="btn-primary" disabled={cur.saving} data-testid="save-currency">
            {cur.saving ? tr(i18n, "common.saving") : tr(i18n, "common.save")}
          </button>
          {cur.msg && (
            <span class="text-sm text-green-700" aria-live="polite">
              {cur.msg}
            </span>
          )}
          {cur.error && (
            <span class="text-sm text-red-700" role="alert">
              {cur.error}
            </span>
          )}
        </form>
      </section>

      {/* ── Badge ────────────────────────────────────────────────────────── */}
      <section class="card p-6" data-testid="badge">
        <h2 class="text-lg font-semibold text-slate-900">{tr(i18n, "pay.badge")}</h2>
        {features.badges ? (
          <>
            <p class="mt-1 text-sm text-slate-500">{tr(i18n, "pay.badgeBody")}</p>
            <img src={data.badge.svg_url} alt="" height="20" class="mt-4 h-5" data-testid="badge-img" />
            <div class="mt-4 space-y-3">
              <CopyField id="badge-markdown" label={tr(i18n, "pay.badgeMarkdown")} value={data.badge.markdown} />
              <CopyField id="badge-html" label={tr(i18n, "pay.badgeHtml")} value={data.badge.html} />
              <CopyField id="badge-shields" label={tr(i18n, "pay.badgeShields")} value={data.badge.shields_url} />
            </div>
            <p class="mt-3 text-xs text-slate-400">{tr(i18n, "pay.badgeStable")}</p>
          </>
        ) : (
          <p class="mt-1 text-sm text-slate-500">{tr(i18n, "pay.badgesOff")}</p>
        )}
      </section>
    </div>
  );
});

export const head: DocumentHead = { title: "Your support — 3m4 payments" };
