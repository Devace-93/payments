import { component$, useContext, useSignal, useStore, useVisibleTask$, $ } from "@builder.io/qwik";
import { Link, useLocation, type DocumentHead } from "@builder.io/qwik-city";
import { api, ApiRequestError, loginUrl } from "../../../lib/api";
import { formatAmount } from "../../../lib/currency";
import { withCacheBust } from "../../../lib/format";
import { FeaturesContext } from "../../../lib/features";
import type { Me, Payment } from "../../../lib/types";
import { CopyField } from "../../../components/copy-field";
import { tr, trError, useI18n } from "../../../i18n";

/** Shown as XXXX-XXXX-XXXX-XXXX; the API normalises (uppercase, strips spaces/dashes). */
function prettyCode(raw: string): string {
  const clean = raw.toUpperCase().replace(/[^0-9A-Z]/g, "").slice(0, 16);
  return clean.replace(/(.{4})(?=.)/g, "$1-");
}

/**
 * `/claim?code=` — the receipt mail links here. Login gate (accounts hosted
 * login, back to this exact URL), then POST /api/claim. Success shows the
 * payment and the badge snippets.
 */
export default component$(() => {
  const loc = useLocation();
  const i18n = useI18n();
  const features = useContext(FeaturesContext);
  const me = useSignal<Me | null>(null);
  const payment = useSignal<Payment | null>(null);
  /** Set when the claim lands: the badge preview must bypass the browser cache (see /me). */
  const badgeRev = useSignal(0);
  const state = useStore({ code: prettyCode(loc.url.searchParams.get("code") || ""), loading: true, busy: false, error: "", gated: false });

  // eslint-disable-next-line qwik/no-use-visible-task
  useVisibleTask$(async () => {
    try {
      const user = await api.getMe();
      if (!user) {
        state.gated = true;
        location.assign(loginUrl(location.href));
        return;
      }
      me.value = user;
    } catch (e) {
      state.error = e instanceof ApiRequestError ? trError(i18n, e.error.code, e.error.message) : tr(i18n, "pay.err.network");
    } finally {
      state.loading = false;
    }
  });

  const submit = $(async () => {
    if (state.busy) return;
    state.error = "";
    const code = state.code.replace(/[^0-9A-Za-z]/g, "");
    if (code.length < 8) {
      state.error = tr(i18n, "pay.err.invalid_code");
      return;
    }
    state.busy = true;
    try {
      const res = await api.claim(code);
      payment.value = res.payment;
      me.value = (await api.getMe().catch(() => me.value)) ?? me.value;
      badgeRev.value = Date.now();
    } catch (e) {
      if (e instanceof ApiRequestError && e.status === 401) {
        location.assign(loginUrl(location.href));
        return;
      }
      state.error = e instanceof ApiRequestError ? trError(i18n, e.error.code, e.error.message) : tr(i18n, "pay.err.network");
    } finally {
      state.busy = false;
    }
  });

  if (state.gated) {
    return (
      <div class="card p-8 text-center">
        <h1 class="text-2xl font-bold text-slate-900">{tr(i18n, "pay.claimTitle")}</h1>
        <p class="mt-2 text-sm text-slate-500">{tr(i18n, "pay.claimSubtitle")}</p>
        <a href={loginUrl()} class="btn-primary mt-6" data-testid="claim-login">
          {tr(i18n, "pay.claimLogin")}
        </a>
      </div>
    );
  }

  const p = payment.value;
  if (p) {
    const badge = me.value?.badge;
    return (
      <div class="card p-8" data-testid="claimed">
        <div class="mx-auto grid h-12 w-12 place-items-center rounded-full bg-green-100 text-2xl" aria-hidden="true">
          ✓
        </div>
        <h1 class="mt-4 text-center text-2xl font-bold text-slate-900">{tr(i18n, "pay.claimedTitle")}</h1>
        <p class="mt-2 text-center text-sm text-slate-600">
          {tr(i18n, "pay.claimedBody", { amount: formatAmount(p.amount, p.currency, i18n.lang), app: p.app })}
        </p>
        {badge && features.badges && (
          <section class="mt-6 space-y-3 border-t border-slate-200 pt-6">
            <h2 class="text-lg font-semibold text-slate-900">{tr(i18n, "pay.badge")}</h2>
            <img src={withCacheBust(badge.svg_url, badgeRev.value)} alt="" height="20" class="h-5" data-testid="badge-img" />
            <CopyField id="badge-markdown" label={tr(i18n, "pay.badgeMarkdown")} value={badge.markdown} />
            <CopyField id="badge-html" label={tr(i18n, "pay.badgeHtml")} value={badge.html} />
          </section>
        )}
        <div class="mt-6 text-center">
          <Link href="/me" class="btn-primary">
            {tr(i18n, "pay.viewSupport")}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div class="card p-8">
      <h1 class="text-2xl font-bold text-slate-900">{tr(i18n, "pay.claimTitle")}</h1>
      <p class="mt-1 text-sm text-slate-500">{tr(i18n, "pay.claimSubtitle")}</p>
      <form class="mt-6 space-y-4" preventdefault:submit onSubmit$={submit}>
        {state.error && (
          <div class="alert-error" role="alert" aria-live="polite" data-testid="error">
            {state.error}
          </div>
        )}
        <div>
          <label class="label" for="code">
            {tr(i18n, "pay.claimCode")}
          </label>
          <input
            id="code"
            type="text"
            class="input font-mono uppercase tracking-widest"
            placeholder="XXXX-XXXX-XXXX-XXXX"
            autoComplete="off"
            spellcheck={false}
            maxLength={19}
            required
            data-testid="code"
            disabled={state.loading || state.busy}
            value={state.code}
            onInput$={(_, el) => {
              state.code = prettyCode(el.value);
              el.value = state.code;
            }}
          />
        </div>
        <button type="submit" class="btn-primary w-full" disabled={state.loading || state.busy} data-testid="submit">
          {state.busy ? tr(i18n, "pay.claiming") : tr(i18n, "pay.claimSubmit")}
        </button>
      </form>
    </div>
  );
});

export const head: DocumentHead = { title: "Claim a donation — 3m4 payments" };
