import { component$, Slot, useStore, useVisibleTask$ } from "@builder.io/qwik";
import { Link, useLocation } from "@builder.io/qwik-city";
import { Logo } from "../../components/logo";
import { Footer } from "../../components/footer";
import { LanguagePicker } from "../../components/language-picker";
import { ThemeToggle } from "../../components/theme-toggle";
import { api, loginUrl, logoutUrl, signupUrl } from "../../lib/api";
import { tr, useI18n } from "../../i18n";

/**
 * Centered card layout for every hosted page (home, donate, subscribe,
 * success, cancel, claim, me): logo + session state + language / theme
 * controls on top, the shared 3m4 footer below. Home and /me get a wider
 * column. Popups opened by pay.js (480 px wide) render the same layout.
 *
 * The session is resolved on the client (`GET /api/me`, null on 401): nothing
 * is rendered in that slot until it is known, so there is no login/handle
 * flash. Logged in → `@handle` (links to /me) + "Log out" through accounts'
 * hosted logout page; logged out → "Your support" + "Log in" / "Sign up",
 * all coming back to the current page.
 */
export default component$(() => {
  const loc = useLocation();
  const i18n = useI18n();
  const path = loc.url.pathname;
  const wide = path === "/" || path.startsWith("/me");
  const session = useStore<{ status: "unknown" | "anon" | "user"; handle: string }>({ status: "unknown", handle: "" });

  // eslint-disable-next-line qwik/no-use-visible-task
  useVisibleTask$(async () => {
    try {
      const me = await api.getMe();
      if (me) {
        session.handle = me.identity.handle;
        session.status = "user";
      } else {
        session.status = "anon";
      }
    } catch {
      session.status = "anon";
    }
  });

  // Absolute URL of the current page (`return_to`). The links below only
  // render once the session is known — on the client — so this is the real
  // browser URL, not the SSR one.
  const here = loc.url.href;

  return (
    <div class="flex min-h-screen flex-col bg-slate-50">
      <header class="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-5">
        <Logo />
        <div class="flex items-center gap-1">
          {session.status === "user" && (
            <>
              <Link
                href="/me"
                class="btn-ghost h-9 max-w-[10rem] font-medium text-slate-900"
                title={tr(i18n, "nav.signedInAs", { handle: session.handle })}
                aria-label={tr(i18n, "nav.signedInAs", { handle: session.handle })}
                data-testid="nav-handle"
              >
                <span class="truncate">@{session.handle}</span>
              </Link>
              <a href={logoutUrl(here)} class="btn-ghost h-9" data-testid="nav-logout">
                {tr(i18n, "nav.logout")}
              </a>
            </>
          )}
          {session.status === "anon" && (
            <>
              {!path.startsWith("/me") && (
                <Link href="/me" class="btn-ghost hidden h-9 sm:inline-flex" data-testid="nav-me">
                  {tr(i18n, "nav.me")}
                </Link>
              )}
              <a href={loginUrl(here)} class="btn-ghost h-9" data-testid="nav-login">
                {tr(i18n, "nav.login")}
              </a>
              <a href={signupUrl(here)} class="btn-secondary h-9" data-testid="nav-signup">
                {tr(i18n, "nav.signup")}
              </a>
            </>
          )}
          <LanguagePicker />
          <ThemeToggle />
        </div>
      </header>
      <main class="flex flex-1 items-start justify-center px-4 py-10 sm:items-center">
        <div class={["w-full", wide ? "max-w-2xl" : "max-w-md"]}>
          <Slot />
        </div>
      </main>
      <Footer />
    </div>
  );
});
