import { component$, useSignal, useStore, useVisibleTask$, $ } from "@builder.io/qwik";
import { Link, useLocation, type DocumentHead } from "@builder.io/qwik-city";
import { api, ApiRequestError, loginUrl, signupUrl } from "../../../lib/api";
import { formatAmount } from "../../../lib/currency";
import { isAllowedReturn } from "../../../lib/returnTo";
import { capture } from "../../../lib/analytics";
import type { Checkout } from "../../../lib/types";
import { AppIcon } from "../../../components/app-icon";
import { tr, trError, useI18n } from "../../../i18n";

const POLL_MS = 2000;
const POLL_MAX_MS = 20_000;

/**
 * `/success?cs=` — Stripe lands here. Polls GET /api/checkout/<cs> every 2 s
 * (up to 20 s) until the webhook has marked it completed, then:
 *   donation, guest     → "we emailed a claim code" + create account / log in
 *   donation, logged in → thanks + link to /me
 *   subscription        → entitlement confirmed + Manage
 * Posts `{type:"m4pay:complete", kind, app, entitlements}` to window.opener
 * (target = the checkout's opener_origin) so pay.js / m4pay.ts can resolve.
 */
export default component$(() => {
  const loc = useLocation();
  const i18n = useI18n();
  const cs = loc.url.searchParams.get("cs") || "";

  const checkout = useSignal<Checkout | null>(null);
  const state = useStore({ phase: "waiting" as "waiting" | "done" | "pending" | "error", error: "", popup: false, posted: false });

  const poll = $(async () => {
    state.phase = "waiting";
    state.error = "";
    const deadline = Date.now() + POLL_MAX_MS;
    while (Date.now() < deadline) {
      try {
        const c = await api.getCheckout(cs);
        checkout.value = c;
        if (c.status === "completed") {
          state.phase = "done";
          if (!state.posted) {
            state.posted = true;
            capture("checkout_completed", { app: c.app.slug, kind: c.kind });
            try {
              if (window.opener && c.opener_origin) {
                window.opener.postMessage({ type: "m4pay:complete", kind: c.kind, app: c.app.slug, entitlements: c.entitlements ?? [] }, c.opener_origin);
              }
            } catch {
              /* the opener may be gone or cross-origin-isolated */
            }
          }
          return;
        }
        if (c.status === "expired") break;
      } catch (e) {
        if (e instanceof ApiRequestError && e.status !== 404 && e.status !== 429) {
          state.error = trError(i18n, e.error.code, e.error.message);
          state.phase = "error";
          return;
        }
      }
      await new Promise((r) => setTimeout(r, POLL_MS));
    }
    state.phase = "pending";
  });

  // eslint-disable-next-line qwik/no-use-visible-task
  useVisibleTask$(() => {
    state.popup = !!window.opener;
    if (!cs) {
      state.phase = "error";
      state.error = tr(i18n, "pay.err.not_found");
      return;
    }
    poll();
  });

  const c = checkout.value;
  const name = c?.app.name ?? "";
  const returnTo = c?.return_to && isAllowedReturn(c.return_to) ? c.return_to : "";
  const claimReturn = typeof location !== "undefined" ? `${location.origin}/claim` : "/claim";

  const back = $(() => {
    if (window.opener) {
      window.close();
      return;
    }
    if (returnTo) location.assign(returnTo);
  });

  if (state.phase === "waiting") {
    return (
      <div class="card p-8 text-center" data-testid="success-waiting">
        <div class="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-primary-200 border-t-primary-600" aria-hidden="true" />
        <h1 class="mt-4 text-xl font-semibold text-slate-900">{tr(i18n, "pay.successWaiting")}</h1>
        <p class="mt-1 text-sm text-slate-500" aria-live="polite">
          {tr(i18n, "pay.successWaitingBody")}
        </p>
      </div>
    );
  }

  if (state.phase === "error") {
    return (
      <div class="card p-8 text-center">
        <p class="text-sm text-red-700" role="alert" data-testid="error">
          {state.error}
        </p>
        <Link href="/" class="btn-secondary mt-4">
          {tr(i18n, "nav.home")}
        </Link>
      </div>
    );
  }

  if (state.phase === "pending") {
    return (
      <div class="card p-8 text-center" data-testid="success-pending">
        <h1 class="text-xl font-semibold text-slate-900">{tr(i18n, "pay.successPending")}</h1>
        <p class="mt-1 text-sm text-slate-500">{tr(i18n, "pay.successPendingBody")}</p>
        <div class="mt-4 flex justify-center gap-2">
          <button type="button" class="btn-secondary" onClick$={poll}>
            {tr(i18n, "common.retry")}
          </button>
          {returnTo && (
            <button type="button" class="btn-ghost" onClick$={back}>
              {tr(i18n, "pay.backTo", { app: name })}
            </button>
          )}
        </div>
      </div>
    );
  }

  // done
  const amount = c ? formatAmount(c.amount, c.currency, i18n.lang) : "";
  return (
    <div class="card p-8 text-center" data-testid="success-done" data-kind={c?.kind}>
      <div class="mx-auto grid h-12 w-12 place-items-center rounded-full bg-green-100 text-2xl" aria-hidden="true">
        ✓
      </div>
      {c && name && (
        <div class="mt-3 flex items-center justify-center gap-2 text-sm text-slate-500" data-testid="success-app">
          <AppIcon name={name} icon={c.app.icon} size="sm" />
          <span>{name}</span>
        </div>
      )}
      {c?.kind === "subscription" ? (
        <>
          <h1 class="mt-4 text-2xl font-bold text-slate-900">{tr(i18n, "pay.subscribedTitle")}</h1>
          <p class="mt-2 text-sm text-slate-600">{tr(i18n, "pay.subscribedBody", { app: name })}</p>
          {c.entitlements?.length > 0 && (
            <p class="mt-1 text-sm text-slate-500" data-testid="entitlements">
              {tr(i18n, "pay.entitlements", { entitlements: c.entitlements.join(", ") })}
            </p>
          )}
          <div class="mt-6 flex flex-wrap justify-center gap-2">
            <Link href="/me" class="btn-primary">
              {tr(i18n, "pay.manage")}
            </Link>
          </div>
        </>
      ) : (
        <>
          <h1 class="mt-4 text-2xl font-bold text-slate-900">{tr(i18n, "pay.thanksTitle")}</h1>
          <p class="mt-2 text-sm text-slate-600">{tr(i18n, "pay.thanksDonation", { amount, app: name })}</p>
          {c?.needs_claim && !c.claimed ? (
            <>
              <p class="mt-2 text-sm text-slate-500" data-testid="claim-explainer">
                {tr(i18n, "pay.thanksGuestBody")}
              </p>
              <div class="mt-6 flex flex-wrap justify-center gap-2">
                <a href={signupUrl(claimReturn)} class="btn-primary" data-testid="create-account">
                  {tr(i18n, "pay.createAccount")}
                </a>
                <a href={loginUrl(claimReturn)} class="btn-secondary" data-testid="log-in">
                  {tr(i18n, "pay.logIn")}
                </a>
              </div>
            </>
          ) : (
            <>
              <p class="mt-2 text-sm text-slate-500">{tr(i18n, "pay.thanksUserBody")}</p>
              <div class="mt-6 flex flex-wrap justify-center gap-2">
                <Link href="/me" class="btn-primary">
                  {tr(i18n, "pay.viewSupport")}
                </Link>
              </div>
            </>
          )}
        </>
      )}

      {(returnTo || state.popup) && (
        <div class="mt-6 border-t border-slate-200 pt-4">
          <button type="button" class="btn-secondary" onClick$={back} data-testid="back-to-app">
            {name ? tr(i18n, "pay.backTo", { app: name }) : tr(i18n, "common.back")}
          </button>
          {state.popup && <p class="mt-2 text-xs text-slate-400">{tr(i18n, "pay.closeHint")}</p>}
        </div>
      )}
    </div>
  );
});

export const head: DocumentHead = { title: "Thank you — 3m4 payments" };
