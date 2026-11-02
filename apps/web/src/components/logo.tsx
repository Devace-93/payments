import { component$ } from "@builder.io/qwik";
import { Link } from "@builder.io/qwik-city";

/** Wordmark for payments (amber square with a coffee-cup + heart mark and "3m4 payments") — links home. */
export const Logo = component$<{ href?: string }>(({ href = "/" }) => {
  return (
    <Link href={href} class="flex items-center gap-2 font-bold tracking-tight">
      <span class="grid h-8 w-8 place-items-center rounded-lg bg-primary-500" aria-hidden="true">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          {/* cup */}
          <path d="M3.5 7.5h10v4.5a4 4 0 0 1-4 4h-2a4 4 0 0 1-4-4z" fill="#1c1917" />
          {/* handle */}
          <path d="M13.5 9h1.2a2 2 0 0 1 0 4h-1.2" stroke="#1c1917" stroke-width="1.6" stroke-linecap="round" />
          {/* steam heart */}
          <path d="M8.5 5.6c-1.3-1.3-3.2 0-2.2 1.4L8.5 9l2.2-2c1-1.4-.9-2.7-2.2-1.4z" fill="#1c1917" fill-opacity="0.8" />
        </svg>
      </span>
      <span class="text-lg text-slate-900">
        3m4 <span class="text-primary-700">payments</span>
      </span>
    </Link>
  );
});
