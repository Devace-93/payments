import { component$ } from "@builder.io/qwik";
import { Link } from "@builder.io/qwik-city";

/** Wordmark for accounts (indigo square with a person + key mark + "accounts") — links home. */
export const Logo = component$<{ href?: string }>(({ href = "/" }) => {
  return (
    <Link href={href} class="flex items-center gap-2 font-bold tracking-tight">
      <span class="grid h-8 w-8 place-items-center rounded-lg bg-primary-600" aria-hidden="true">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          {/* head */}
          <circle cx="8" cy="6.5" r="3" fill="#ffffff" />
          {/* shoulders */}
          <path d="M2.5 16.5c0-3.3 2.5-5.5 5.5-5.5s5.5 2.2 5.5 5.5" fill="#ffffff" fill-opacity="0.85" />
          {/* key */}
          <circle cx="15" cy="9.5" r="2.1" stroke="#ffffff" stroke-width="1.6" />
          <path d="M15 11.6v5m0-2h2m-2-1.4h1.6" stroke="#ffffff" stroke-width="1.6" stroke-linecap="round" />
        </svg>
      </span>
      <span class="text-lg text-slate-900">
        <span class="text-primary-600">accounts</span>
      </span>
    </Link>
  );
});
