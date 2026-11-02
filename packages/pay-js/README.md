# pay.js

Drop-in donate / subscribe button for the static 3m4 apps (info, kinegram,
bubbles, the MouseTouch site). Zero dependencies, under 5 KB gzipped, served by
the payments web service at `https://payments.3m4.net/pay.js` (CORS `*`,
`max-age=300`). See CONTRACT.md §10.

```html
<!-- one-time donation, default label "Buy me a coffee" / "Invítame un café" -->
<script src="https://payments.3m4.net/pay.js" data-app="retro" data-kind="donate"
        data-amount="500" data-currency="usd" data-label="Buy me a coffee" data-mount="#support" defer></script>

<!-- subscription (login gate happens on payments; needs a 3m4 account) -->
<script src="https://payments.3m4.net/pay.js" data-app="retro" data-kind="subscribe"
        data-price="pro_monthly" data-return-to="https://retro.3m4.net/dashboard/billing" defer></script>
```

| Attribute | Meaning |
|---|---|
| `data-app` | app slug from `packages/shared/catalog.json` (required) |
| `data-kind` | `donate` (default) or `subscribe` |
| `data-amount`, `data-currency` | donation preset in minor units (`500` = $5.00) and `usd` / `mxn` / `eur` |
| `data-price` | product key for `subscribe` (e.g. `pro_monthly`) |
| `data-label` | button text (default from `3m4.lang`: en / es) |
| `data-return-to` | where "Back to {app}" goes (default: the current page) |
| `data-mount` | CSS selector; without it the button is inserted right after the script tag |
| `data-lang` | forwarded to the donate page (default from `3m4.lang`) |

- One button per tag; every tag shares one `window.m4pay = { open, entitlements, origin }`.
- Click → popup `window.open(url, "m4pay", "popup,width=480,height=780")`; when
  the popup is blocked the page navigates to the hosted page instead
  (`return_to` brings the user back).
- The success page posts `{type:"m4pay:complete", kind, app, entitlements}` to
  the opener; pay.js accepts it **only from the payments origin** and dispatches
  `window.dispatchEvent(new CustomEvent("m4pay:paid", { detail }))` with
  `detail = { kind, app, entitlements, via: "message" | "poll" }`.
- For `subscribe` it also polls `GET /api/entitlements?app=` (credentials) when
  the host window regains focus, 10 × 3 s, because COOP can null `window.opener`
  after the Stripe hop. A change in the entitlement set fires `m4pay:paid` too.
- Theme follows `data-theme` on `<html>`, `localStorage["3m4.theme"]` or the
  system preference; the host's `--accent` CSS variable colours the button.
- Nothing in here throws into the host page.

```js
window.addEventListener("m4pay:paid", (e) => console.log("paid", e.detail));
window.m4pay.open({ app: "retro", kind: "donate", amount: 1000, currency: "mxn" });
```

## Build

```bash
bun install
bun run build       # → apps/web/public/pay.js (gitignored, rebuilt by the web Dockerfile)
bun run typecheck
```

`demo.html` is a host page with one donate and one subscribe button pointing
at `http://localhost:8086`: open it next to a running stack (`make up`).
