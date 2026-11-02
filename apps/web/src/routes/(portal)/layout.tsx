import { component$, Slot } from "@builder.io/qwik";
import { Link, useLocation } from "@builder.io/qwik-city";
import { Logo } from "../../components/logo";
import { Footer } from "../../components/footer";
import { LanguagePicker } from "../../components/language-picker";
import { ThemeToggle } from "../../components/theme-toggle";
import { tr, useI18n } from "../../i18n";

/**
 * Centered card layout for every hosted page (home, donate, subscribe,
 * success, cancel, claim, me): logo + "Your support" link + language / theme
 * controls on top, the shared 3m4 footer below. Home and /me get a wider
 * column. Popups opened by pay.js (480 px wide) render the same layout.
 */
export default component$(() => {
  const loc = useLocation();
  const i18n = useI18n();
  const path = loc.url.pathname;
  const wide = path === "/" || path.startsWith("/me");
  return (
    <div class="flex min-h-screen flex-col bg-slate-50">
      <header class="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-5">
        <Logo />
        <div class="flex items-center gap-1">
          {!path.startsWith("/me") && (
            <Link href="/me" class="btn-ghost hidden h-9 sm:inline-flex" data-testid="nav-me">
              {tr(i18n, "nav.me")}
            </Link>
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
