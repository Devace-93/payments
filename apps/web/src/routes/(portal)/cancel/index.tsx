import { component$, useSignal, useStore, useVisibleTask$ } from "@builder.io/qwik";
import { Link, useLocation, type DocumentHead } from "@builder.io/qwik-city";
import { api, ApiRequestError } from "../../../lib/api";
import { isAllowedReturn } from "../../../lib/returnTo";
import type { Checkout } from "../../../lib/types";
import { tr, trError, useI18n } from "../../../i18n";

/**
 * `/cancel?id=` — Stripe's cancel_url. Reads the checkout to rebuild a retry
 * link (`/donate` or `/subscribe` with the same app / amount / currency) and
 * a "Back to {app}" link from its `return_to`.
 */
export default component$(() => {
  const loc = useLocation();
  const i18n = useI18n();
  const id = loc.url.searchParams.get("id") || "";
  const checkout = useSignal<Checkout | null>(null);
  const state = useStore({ loading: !!id, error: "" });

  // eslint-disable-next-line qwik/no-use-visible-task
  useVisibleTask$(async () => {
    if (!id) return;
    try {
      checkout.value = await api.getCheckout(id);
    } catch (e) {
      state.error = e instanceof ApiRequestError ? trError(i18n, e.error.code, e.error.message) : tr(i18n, "pay.err.network");
    } finally {
      state.loading = false;
    }
  });

  const c = checkout.value;
  const name = c?.app.name ?? "";
  const returnTo = c?.return_to && isAllowedReturn(c.return_to) ? c.return_to : "";
  let retry = "/";
  if (c) {
    const p = new URLSearchParams({ app: c.app.slug, currency: c.currency });
    if (c.return_to) p.set("return_to", c.return_to);
    if (c.opener_origin) p.set("origin", c.opener_origin);
    if (c.kind === "subscription") {
      if (c.price) p.set("price", c.price);
      retry = c.price ? `/subscribe?${p}` : `/?${p}`;
    } else {
      if (c.amount) p.set("amount", String(c.amount));
      retry = `/donate?${p}`;
    }
  }

  return (
    <div class="card p-8 text-center" data-testid="cancel">
      <h1 class="text-2xl font-bold text-slate-900">{tr(i18n, c?.status === "expired" ? "pay.expiredTitle" : "pay.cancelTitle")}</h1>
      <p class="mt-2 text-sm text-slate-500">{tr(i18n, "pay.cancelBody")}</p>
      {state.error && (
        <p class="mt-3 text-sm text-red-700" role="alert" data-testid="error">
          {state.error}
        </p>
      )}
      {state.loading && <p class="mt-3 text-sm text-slate-400">{tr(i18n, "common.loading")}</p>}
      <div class="mt-6 flex flex-wrap justify-center gap-2">
        <Link href={retry} class="btn-primary" data-testid="retry">
          {tr(i18n, "pay.tryAgain")}
        </Link>
        {returnTo && (
          <a href={returnTo} class="btn-secondary" data-testid="back-to-app">
            {tr(i18n, "pay.backTo", { app: name })}
          </a>
        )}
      </div>
    </div>
  );
});

export const head: DocumentHead = { title: "Payment cancelled — 3m4 payments" };
