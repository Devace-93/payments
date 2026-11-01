/**
 * session.js — the 3m4 accounts widget for static apps (info, kinegram,
 * bubbles). See CONTRACT.md → "session.js widget".
 *
 *   <div id="session"></div>
 *   <script src="https://accounts.3m4.net/session.js" data-mount="#session" defer></script>
 *
 * Signed out: "Log in · Sign up" links to the hosted pages with
 * return_to=location.href. Signed in: avatar + handle; clicking opens a menu
 * with Profile and Log out. Strings follow `3m4.lang` (en / es), the theme
 * follows `3m4.theme` / prefers-color-scheme, and the host's `--accent` CSS
 * variable is used when present. Also exposes `window.m4session`.
 *
 * Everything is wrapped so that a failure here never throws into the host.
 */
interface User {
  id: string;
  email: string;
  email_verified: boolean;
  handle: string;
  name: string | null;
  avatar_url: string;
}

interface M4Session {
  get(force?: boolean): Promise<User | null>;
  onChange(cb: (user: User | null) => void): () => void;
  login(returnTo?: string): void;
  signup(returnTo?: string): void;
  logout(): Promise<void>;
  profile(): void;
  origin: string;
}

declare global {
  interface Window {
    m4session?: M4Session;
  }
}

const STRINGS = {
  en: { login: "Log in", signup: "Sign up", profile: "Profile", logout: "Log out", menu: "Account menu" },
  es: { login: "Iniciar sesión", signup: "Regístrate", profile: "Perfil", logout: "Cerrar sesión", menu: "Menú de cuenta" },
};

(() => {
  try {
    if (window.m4session) return;
    const script = document.currentScript as HTMLScriptElement | null;
    const origin = new URL(script?.src || location.href, location.href).origin;
    const api = origin + "/api";

    // ---- strings / theme ---------------------------------------------------
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
    const t = (k: keyof typeof STRINGS.en) => STRINGS[lang()][k];
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

    // ---- state ---------------------------------------------------------------
    let user: User | null = null;
    let known = false;
    let inFlight: Promise<User | null> | null = null;
    const listeners = new Set<(u: User | null) => void>();
    const notify = () => {
      listeners.forEach((cb) => {
        try {
          cb(user);
        } catch {
          /* host callback errors are not ours */
        }
      });
      render();
    };

    const call = (path: string, init?: RequestInit) =>
      fetch(api + path, { credentials: "include", headers: { "Content-Type": "application/json" }, ...init });

    const fetchSession = async (): Promise<User | null> => {
      let res = await call("/session");
      if (res.status === 401) {
        let code = "";
        try {
          code = (await res.clone().json()).error?.code || "";
        } catch {
          /* no body */
        }
        if (code === "session_expired") {
          const r = await call("/session/refresh", { method: "POST", body: "{}" });
          if (r.ok) res = await call("/session");
        }
      }
      if (!res.ok) return null;
      return ((await res.json()) as { user: User }).user;
    };

    const get = (force = false): Promise<User | null> => {
      if (known && !force) return Promise.resolve(user);
      if (inFlight) return inFlight;
      inFlight = fetchSession()
        .catch(() => (known ? user : null))
        .then((u) => {
          const changed = !known || (u?.id ?? null) !== (user?.id ?? null) || u?.avatar_url !== user?.avatar_url;
          user = u;
          known = true;
          inFlight = null;
          if (changed) notify();
          return u;
        });
      return inFlight;
    };

    const here = () => location.href;
    const page = (path: string, returnTo?: string) =>
      origin + path + "?return_to=" + encodeURIComponent(returnTo || here());
    const login = (rt?: string) => location.assign(page("/login", rt));
    const signup = (rt?: string) => location.assign(page("/signup", rt));
    const profile = () => location.assign(page("/profile"));
    const logout = async () => {
      try {
        await call("/session/logout", { method: "POST", body: "{}" });
      } catch {
        /* offline: the cookie will expire on its own */
      }
      user = null;
      known = true;
      notify();
    };

    // ---- rendering -----------------------------------------------------------
    const css = `
.m4s{--m4s-a:var(--accent,#4f46e5);--m4s-bg:#fff;--m4s-fg:#1b1c22;--m4s-dim:#5c6070;--m4s-br:#e3e3ec;--m4s-hv:#f0f0f8;font:500 14px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;display:inline-flex;align-items:center;gap:6px;position:relative;color:var(--m4s-fg)}
.m4s[data-dark]{--m4s-bg:#15171e;--m4s-fg:#e8e9ed;--m4s-dim:#9a9ea9;--m4s-br:#262a35;--m4s-hv:#1b1e27}
.m4s a,.m4s button{font:inherit;color:inherit;text-decoration:none;cursor:pointer;background:var(--m4s-bg);border:1px solid var(--m4s-br);border-radius:999px;padding:6px 12px;display:inline-flex;align-items:center;gap:8px}
.m4s a:hover,.m4s button:hover{background:var(--m4s-hv);border-color:var(--m4s-a)}
.m4s .m4s-p{background:var(--m4s-a);border-color:var(--m4s-a);color:#fff}
.m4s .m4s-p:hover{filter:brightness(1.08);background:var(--m4s-a)}
.m4s img{width:24px;height:24px;border-radius:50%;object-fit:cover;background:var(--m4s-hv)}
.m4s .m4s-u{padding:3px 12px 3px 3px;max-width:14em}
.m4s .m4s-u span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.m4s .m4s-m{position:absolute;top:calc(100% + 6px);inset-inline-end:0;min-width:11em;background:var(--m4s-bg);border:1px solid var(--m4s-br);border-radius:12px;padding:6px;box-shadow:0 10px 30px rgba(0,0,0,.15);display:flex;flex-direction:column;gap:2px;z-index:2147483000}
.m4s .m4s-m a,.m4s .m4s-m button{border:0;border-radius:8px;padding:8px 10px;background:none;justify-content:flex-start;width:100%}
.m4s .m4s-m a:hover,.m4s .m4s-m button:hover{background:var(--m4s-hv)}
.m4s-float{position:fixed;top:16px;inset-inline-end:16px;z-index:2147482999}
`;
    let root: HTMLElement | null = null;
    let open = false;

    const mount = () => {
      if (root) return root;
      const sel = script?.getAttribute("data-mount");
      let host = sel ? (document.querySelector(sel) as HTMLElement | null) : null;
      if (!host) {
        host = document.createElement("div");
        host.className = "m4s-float";
        document.body.appendChild(host);
      }
      const style = document.createElement("style");
      style.textContent = css;
      document.head.appendChild(style);
      root = document.createElement("div");
      root.className = "m4s";
      host.appendChild(root);
      document.addEventListener("click", (e) => {
        // render() rebuilds the nodes, so a click on the (now detached) toggle
        // must not count as an outside click.
        const t = e.target as Node;
        if (open && root && document.contains(t) && !root.contains(t)) {
          open = false;
          render();
        }
      });
      return root;
    };

    const el = <K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string>, text?: string) => {
      const n = document.createElement(tag);
      for (const k in attrs) n.setAttribute(k, attrs[k]);
      if (text) n.textContent = text;
      return n;
    };

    const render = () => {
      const r = mount();
      r.textContent = "";
      if (dark()) r.setAttribute("data-dark", "");
      else r.removeAttribute("data-dark");
      if (!known) return;
      if (!user) {
        r.appendChild(el("a", { href: page("/login"), "data-m4s": "login" }, t("login")));
        r.appendChild(el("a", { href: page("/signup"), class: "m4s-p", "data-m4s": "signup" }, t("signup")));
        return;
      }
      const b = el("button", { type: "button", class: "m4s-u", "aria-haspopup": "menu", "aria-expanded": String(open), "aria-label": t("menu"), "data-m4s": "user" });
      b.appendChild(el("img", { src: user.avatar_url, alt: user.name || user.handle, width: "24", height: "24" }));
      b.appendChild(el("span", {}, "@" + user.handle));
      b.onclick = () => {
        open = !open;
        render();
      };
      r.appendChild(b);
      if (open) {
        const m = el("div", { class: "m4s-m", role: "menu" });
        m.appendChild(el("a", { href: page("/profile"), role: "menuitem", "data-m4s": "profile" }, t("profile")));
        const lo = el("button", { type: "button", role: "menuitem", "data-m4s": "logout" }, t("logout"));
        lo.onclick = () => {
          open = false;
          logout();
        };
        m.appendChild(lo);
        r.appendChild(m);
      }
    };

    // ---- public API + lifecycle ----------------------------------------------
    window.m4session = {
      get,
      onChange(cb) {
        listeners.add(cb);
        if (known) {
          try {
            cb(user);
          } catch {
            /* ignore */
          }
        }
        return () => listeners.delete(cb);
      },
      login,
      signup,
      logout,
      profile,
      origin,
    };

    const start = () => {
      try {
        mount();
        get();
      } catch {
        /* never into the host */
      }
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
    else start();
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") get(true);
    });
    window.addEventListener("storage", (e) => {
      if (e.key === "3m4.lang" || e.key === "3m4.theme") render();
    });
    new MutationObserver(() => render()).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "lang"] });
  } catch {
    /* never throw into the host page */
  }
})();

export {};
