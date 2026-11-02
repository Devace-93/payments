/**
 * pay.js — the 3m4 payments button for static apps (CONTRACT.md §10).
 *
 *   <script src="https://payments.3m4.net/pay.js" data-app="retro" data-kind="donate"
 *           data-amount="500" data-currency="usd" data-label="Buy me a coffee" data-mount="#support" defer></script>
 *   <script src="https://payments.3m4.net/pay.js" data-app="retro" data-kind="subscribe"
 *           data-price="pro_monthly" data-return-to="https://retro.3m4.net/dashboard/billing" defer></script>
 *   <script src="https://payments.3m4.net/pay.js" data-app="retro" data-kind="supporters"
 *           data-limit="24" data-label="Thanks to our supporters" data-mount="#supporters" defer></script>
 *
 * `data-kind="supporters"` renders the public supporters list of the app
 * (`GET /api/public/supporters?app=`: opted-in donors / subscribers plus
 * GitHub sponsors) as a row of chips; nothing is rendered while the list is
 * empty. It is not gated by the paying switches (public data).
 *
 * One button per tag (`data-mount` selector, else inserted after the script).
 * Click → popup `window.open(url, "m4pay", "popup,width=480,height=780")`;
 * blocked → `location.assign(url)`. Accepts `message` events only from the
 * payments origin with `data.type === "m4pay:complete"` and dispatches a
 * `window` CustomEvent `m4pay:paid` with that `detail`. For `subscribe` it also
 * polls `GET /api/entitlements?app=` (credentials) on `focus`, up to 10 × 3 s,
 * because COOP may null `window.opener` after the Stripe hop. Theme / lang from
 * `localStorage 3m4.theme` / `3m4.lang` (en / es, en fallback). Exposes
 * `window.m4pay = { open, entitlements, origin }`. Never throws into the host.
 */
interface Entitlements {
  app: string;
  entitlements: string[];
  subscription: { status: string; current_period_end: string | null; cancel_at_period_end: boolean } | null;
  updated_at: string;
}

interface PaidDetail {
  kind: "donation" | "subscription";
  app: string;
  entitlements: string[];
  via: "message" | "poll";
}

interface OpenOpts {
  app: string;
  kind: "donate" | "subscribe";
  amount?: number | string;
  currency?: string;
  price?: string;
  returnTo?: string;
  lang?: string;
}

interface Supporter {
  display_name: string;
  handle: string | null;
  tier: "supporter" | "pro" | "team";
  since: string | null;
  message: string | null;
  source?: "stripe" | "github";
  url?: string | null;
  avatar_url?: string | null;
}

interface M4Pay {
  open(opts: OpenOpts): Window | null;
  entitlements(app: string): Promise<Entitlements | null>;
  supporters(app: string, limit?: number): Promise<Supporter[]>;
  origin: string;
}

declare global {
  interface Window {
    m4pay?: M4Pay;
  }
}

const STRINGS = {
  en: { donate: "Buy me a coffee", subscribe: "Subscribe", opening: "Opening…", supporters: "Thanks to our supporters" },
  es: { donate: "Invítame un café", subscribe: "Suscribirse", opening: "Abriendo…", supporters: "Gracias a quienes nos apoyan" },
};

const CSS = `
.m4p{--m4p-a:var(--accent,#f59e0b);--m4p-fg:#1c1917;font:600 14px/1.2 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;display:inline-flex;align-items:center;gap:8px;cursor:pointer;border:0;border-radius:999px;padding:9px 16px;background:var(--m4p-a);color:var(--m4p-fg);text-decoration:none;transition:filter .15s}
.m4p:hover{filter:brightness(1.06)}.m4p:focus-visible{outline:2px solid var(--m4p-a);outline-offset:2px}.m4p[disabled]{opacity:.7;cursor:progress}
.m4p[data-dark]{box-shadow:0 0 0 1px rgba(255,255,255,.08)}
.m4p svg{width:16px;height:16px;flex:none}
.m4p-sup{--m4p-a:var(--accent,#f59e0b);font:500 13px/1.3 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:inherit}
.m4p-sup-title{display:block;margin:0 0 8px;font-weight:600;opacity:.8}
.m4p-sup-list{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.m4p-sup-list a,.m4p-sup-list span.m4p-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px 4px 4px;border-radius:999px;background:rgba(127,127,127,.12);color:inherit;text-decoration:none;max-width:100%}
.m4p-sup-list a:hover{background:rgba(127,127,127,.22)}
.m4p-sup-list img,.m4p-sup-list i{width:22px;height:22px;border-radius:50%;flex:none;object-fit:cover}
.m4p-sup-list i{display:inline-grid;place-items:center;font:700 11px/1 system-ui,sans-serif;font-style:normal;background:var(--m4p-a);color:#1c1917}
.m4p-sup-list b{font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.m4p-sup-list [data-tier="pro"] i,.m4p-sup-list [data-tier="team"] i{box-shadow:0 0 0 2px var(--m4p-a)}
`;

(() => {
  try {
    const script = document.currentScript as HTMLScriptElement | null;
    if (!script) return;
    const origin = new URL(script.src, location.href).origin;

    // ---- shared singleton (one per payments origin) -------------------------
    const shared = (() => {
      if (window.m4pay && window.m4pay.origin === origin) return window.m4pay;

      const lang = (): keyof typeof STRINGS => {
        let l = "";
        try {
          l = localStorage.getItem("3m4.lang") || "";
        } catch {
          /* storage unavailable */
        }
        l = (l || document.documentElement.lang || navigator.language || "en").slice(0, 2);
        return l === "es" ? "es" : "en";
      };
      // The viewer's full locale (e.g. es-MX) so the portal opens in the same
      // language the host page shows; `lang()` above is only for our two strings.
      const fullLang = (): string => {
        let l = "";
        try {
          l = localStorage.getItem("3m4.lang") || "";
        } catch {
          /* storage unavailable */
        }
        return l || document.documentElement.lang || navigator.language || "en";
      };
      const dark = (): boolean => {
        let th = document.documentElement.dataset.theme || "";
        if (!th) {
          try {
            th = localStorage.getItem("3m4.theme") || "";
          } catch {
            /* ignore */
          }
        }
        if (th === "dark" || th === "light") return th === "dark";
        return typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches;
      };

      const entitlements = async (app: string): Promise<Entitlements | null> => {
        try {
          const res = await fetch(`${origin}/api/entitlements?app=${encodeURIComponent(app)}`, { credentials: "include" });
          if (!res.ok) return null;
          return (await res.json()) as Entitlements;
        } catch {
          return null;
        }
      };

      // Gated rollout: the paying switches are evaluated per viewer by the
      // portal (PostHog distinct_id = the accounts sub). One request per page;
      // a failed request hides the buttons rather than showing a dead end.
      let featuresPromise: Promise<Record<string, boolean>> | null = null;
      const features = (): Promise<Record<string, boolean>> => {
        if (!featuresPromise) {
          featuresPromise = fetch(`${origin}/api/features`, { credentials: "include" })
            .then((r) => (r.ok ? (r.json() as Promise<{ features?: Record<string, boolean> }>) : {}))
            .then((d: { features?: Record<string, boolean> }) => d.features || {})
            .catch(() => ({}) as Record<string, boolean>);
        }
        return featuresPromise;
      };
      const allowed = async (kind: "donate" | "subscribe"): Promise<boolean> => {
        const f = await features();
        return !!f[kind === "donate" ? "donations" : "subscriptions"];
      };

      const paid = (detail: PaidDetail) => {
        try {
          window.dispatchEvent(new CustomEvent("m4pay:paid", { detail }));
        } catch {
          /* host listeners are not ours */
        }
      };

      // Pending subscription flows: app → snapshot of entitlements before.
      const pending = new Map<string, string>();
      let pollTimer: ReturnType<typeof setTimeout> | null = null;
      let polls = 0;
      const poll = async () => {
        pollTimer = null;
        if (!pending.size) return;
        polls++;
        for (const [app, before] of Array.from(pending)) {
          const ent = await entitlements(app);
          if (!ent) continue;
          const now = JSON.stringify(ent.entitlements.slice().sort());
          if (now !== before && ent.entitlements.length) {
            pending.delete(app);
            paid({ kind: "subscription", app, entitlements: ent.entitlements, via: "poll" });
          }
        }
        if (pending.size && polls < 10) pollTimer = setTimeout(poll, 3000);
      };
      window.addEventListener("focus", () => {
        if (pending.size && !pollTimer) {
          polls = 0;
          poll();
        }
      });
      window.addEventListener("message", (e: MessageEvent) => {
        if (e.origin !== origin) return;
        const d = e.data as Partial<PaidDetail> & { type?: string };
        if (!d || d.type !== "m4pay:complete") return;
        const app = d.app || "";
        pending.delete(app);
        paid({ kind: d.kind === "subscription" ? "subscription" : "donation", app, entitlements: d.entitlements || [], via: "message" });
      });

      const url = (o: OpenOpts): string => {
        const p = new URLSearchParams({ app: o.app, origin: location.origin, return_to: o.returnTo || location.href });
        if (o.currency) p.set("currency", o.currency);
        if (o.kind === "subscribe") {
          if (o.price) p.set("price", o.price);
        } else {
          if (o.amount) p.set("amount", String(o.amount));
          p.set("lang", o.lang || fullLang());
        }
        return `${origin}/${o.kind === "subscribe" ? "subscribe" : "donate"}?${p}`;
      };

      const open = (o: OpenOpts): Window | null => {
        const u = url(o);
        if (o.kind === "subscribe") {
          pending.set(o.app, "?");
          entitlements(o.app).then((ent) => {
            if (pending.has(o.app)) pending.set(o.app, JSON.stringify((ent?.entitlements || []).slice().sort()));
          });
        }
        const w = window.open(u, "m4pay", "popup,width=480,height=780");
        if (!w) {
          location.assign(u);
          return null;
        }
        try {
          w.focus();
        } catch {
          /* ignore */
        }
        return w;
      };

      const supporters = async (app: string, limit = 24): Promise<Supporter[]> => {
        try {
          const res = await fetch(`${origin}/api/public/supporters?app=${encodeURIComponent(app)}&limit=${Math.max(1, Math.min(limit, 200))}`);
          if (!res.ok) return [];
          const d = (await res.json()) as { items?: Supporter[] };
          return Array.isArray(d.items) ? d.items : [];
        } catch {
          return [];
        }
      };

      const api: M4Pay & { _t: typeof STRINGS.en; _dark: () => boolean } = {
        open,
        entitlements,
        supporters,
        origin,
        get _t() {
          return STRINGS[lang()];
        },
        _dark: dark,
      };
      window.m4pay = api;
      const style = document.createElement("style");
      style.textContent = CSS;
      document.head.appendChild(style);
      (api as unknown as { _allowed: typeof allowed })._allowed = allowed;
      return api;
    })() as M4Pay & { _t: typeof STRINGS.en; _dark: () => boolean; _allowed: (kind: "donate" | "subscribe") => Promise<boolean> };

    // ---- this tag's button -------------------------------------------------
    const d = script.dataset;
    const app = d.app || "";
    if (!app) return;

    const place = (el: HTMLElement) => {
      try {
        const sel = d.mount;
        const host = sel ? document.querySelector(sel) : null;
        if (host) host.appendChild(el);
        else if (script.parentNode) script.parentNode.insertBefore(el, script.nextSibling);
        else document.body.appendChild(el);
      } catch {
        /* ignore */
      }
    };

    if (d.kind === "supporters") {
      // ---- supporters list (public, not gated) ----------------------------
      const box = document.createElement("div");
      box.className = "m4p-sup";
      box.setAttribute("data-m4pay", "supporters");
      const title = document.createElement("span");
      title.className = "m4p-sup-title";
      const list = document.createElement("ul");
      list.className = "m4p-sup-list";
      box.appendChild(title);
      box.appendChild(list);
      const renderTitle = () => {
        title.textContent = d.label || shared._t.supporters;
        if (shared._dark()) box.setAttribute("data-dark", "");
        else box.removeAttribute("data-dark");
      };
      const initial = (s: Supporter) => (s.display_name || s.handle || "?").trim().charAt(0).toUpperCase() || "?";
      const fill = (items: Supporter[]) => {
        list.textContent = "";
        for (const s of items) {
          const li = document.createElement("li");
          li.setAttribute("data-tier", s.tier || "supporter");
          const chip = s.url ? document.createElement("a") : document.createElement("span");
          if (s.url && chip instanceof HTMLAnchorElement) {
            chip.href = s.url;
            chip.target = "_blank";
            chip.rel = "noopener nofollow";
          } else chip.className = "m4p-chip";
          if (s.avatar_url) {
            const img = document.createElement("img");
            img.src = s.avatar_url;
            img.alt = "";
            img.loading = "lazy";
            img.referrerPolicy = "no-referrer";
            chip.appendChild(img);
          } else {
            const i = document.createElement("i");
            i.textContent = initial(s);
            chip.appendChild(i);
          }
          const b = document.createElement("b");
          b.textContent = s.display_name || (s.handle ? `@${s.handle}` : "anonymous");
          chip.appendChild(b);
          if (s.message) chip.title = s.message;
          li.appendChild(chip);
          list.appendChild(li);
        }
      };
      const mountList = () => {
        shared.supporters(app, Number(d.limit) || 24).then((items) => {
          if (!items.length) return; // nothing to show: stay invisible
          renderTitle();
          fill(items);
          place(box);
        });
      };
      if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountList);
      else mountList();
      window.addEventListener("storage", (e) => {
        if (e.key === "3m4.lang" || e.key === "3m4.theme") renderTitle();
      });
      new MutationObserver(renderTitle).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "lang"] });
      return;
    }

    const kind: "donate" | "subscribe" = d.kind === "subscribe" ? "subscribe" : "donate";
    const opts: OpenOpts = { app, kind, amount: d.amount, currency: d.currency, price: d.price, returnTo: d.returnTo, lang: d.lang };

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "m4p";
    btn.setAttribute("data-m4pay", kind);
    const icon =
      kind === "donate"
        ? '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M3.5 7.5h10v4.5a4 4 0 0 1-4 4h-2a4 4 0 0 1-4-4z" fill="currentColor"/><path d="M13.5 9h1.2a2 2 0 0 1 0 4h-1.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M8.5 5.6c-1.3-1.3-3.2 0-2.2 1.4L8.5 9l2.2-2c1-1.4-.9-2.7-2.2-1.4z" fill="currentColor" opacity=".8"/></svg>'
        : '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 2.5l2.2 4.6 5 .7-3.6 3.5.9 5-4.5-2.4-4.5 2.4.9-5L2.8 7.8l5-.7z" fill="currentColor"/></svg>';
    const label = document.createElement("span");
    const render = () => {
      label.textContent = d.label || shared._t[kind];
      if (shared._dark()) btn.setAttribute("data-dark", "");
      else btn.removeAttribute("data-dark");
    };
    btn.innerHTML = icon;
    btn.appendChild(label);
    render();
    btn.onclick = () => {
      try {
        shared.open(opts);
      } catch {
        /* never into the host */
      }
    };

    const mount = () => place(btn);
    const mountWhenAllowed = () => {
      shared._allowed(kind).then((ok) => {
        if (ok) mount();
      });
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountWhenAllowed);
    else mountWhenAllowed();

    window.addEventListener("storage", (e) => {
      if (e.key === "3m4.lang" || e.key === "3m4.theme") render();
    });
    new MutationObserver(render).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "lang"] });
  } catch {
    /* never throw into the host page */
  }
})();

export {};
