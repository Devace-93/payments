# session.js

Drop-in login / avatar widget for the static 3m4 apps (info, kinegram,
bubbles). Zero dependencies, under 4 KB gzipped, served by the accounts web
service at `https://accounts.3m4.net/session.js`.

```html
<div id="session"></div>
<script src="https://accounts.3m4.net/session.js" data-mount="#session" defer></script>
```

- **Signed out:** `Log in` · `Sign up` links to the hosted pages, with
  `return_to` set to the current page.
- **Signed in:** avatar + `@handle`; clicking opens a menu with `Profile` and
  `Log out`.
- Without `data-mount` (or when the selector matches nothing) it floats in the
  top-right corner.
- Strings follow `localStorage["3m4.lang"]` (en / es, falls back to en); the
  theme follows `data-theme` on `<html>`, `localStorage["3m4.theme"]` or the
  system preference; the host's `--accent` CSS variable colours the primary
  button when defined.
- The accounts origin is taken from the script's own `src`, so the same tag
  works against `http://localhost:8085/session.js` in development.

## `window.m4session`

| Member | Does |
|---|---|
| `get(force?)` | `Promise<User \| null>`; cached, re-fetched when the tab becomes visible or with `force` |
| `onChange(cb)` | calls `cb(user)` now (if known) and on every change; returns an unsubscribe function |
| `login(returnTo?)` / `signup(returnTo?)` / `profile()` | navigate to the hosted pages |
| `logout()` | `POST /api/session/logout` with credentials, then notifies |
| `origin` | the accounts origin the widget talks to |

`User` is `{ id, email, email_verified, handle, name, avatar_url }` (see
`CONTRACT.md`). Requests go to `GET /api/session` with `credentials: "include"`;
on `401 session_expired` one `POST /api/session/refresh` is attempted. Nothing
in here throws into the host page.

## Build

```bash
bun install
bun run build   # → apps/web/public/session.js (gitignored, rebuilt by the web Dockerfile)
```

`demo.html` is a tiny host page: open it next to a running stack
(`make up`, http://localhost:8085) to see both states.
