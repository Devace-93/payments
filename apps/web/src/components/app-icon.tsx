import { component$ } from "@builder.io/qwik";

/**
 * Small rounded app icon shown next to an app's name (home, donate, subscribe,
 * success). Renders the catalog's `app.icon` when present, else a neutral tile
 * with the app's initial. Decorative: the name is always written next to it.
 */
export const AppIcon = component$<{ name: string; icon?: string | null; size?: "sm" | "md" }>(({ name, icon, size = "md" }) => {
  const box = size === "sm" ? "h-8 w-8 rounded-md text-xs" : "h-9 w-9 rounded-lg text-sm";
  if (icon) {
    return <img src={icon} alt="" width={size === "sm" ? 32 : 36} height={size === "sm" ? 32 : 36} loading="lazy" decoding="async" class={["shrink-0 object-cover", box]} data-testid="app-icon" />;
  }
  return (
    <span aria-hidden="true" class={["grid shrink-0 select-none place-items-center bg-slate-100 font-semibold uppercase text-slate-600", box]} data-testid="app-icon">
      {(name.trim()[0] ?? "?").toUpperCase()}
    </span>
  );
});
