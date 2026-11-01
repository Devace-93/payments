# accounts e2e

Playwright suite against a running stack (`make up`, then `make e2e`). Each spec
creates its own users through the API or the forms; nothing is shared or reused
between runs. Mails are read back from Mailpit's JSON API (`http://localhost:8025`),
so the local `.env` needs `MAIL_ENABLED=true` and `SMTP_URL=smtp://mailpit:1025`
(the CI recipe in `.github/workflows/e2e.yml` sets both). Set `E2E_BASE_URL` /
`E2E_MAILPIT_URL` to point at another host.

| Spec | Covers |
|---|---|
| `signup.spec.ts` | handle derived from the email, show/hide toggles on both password fields, mismatch, sign up → `/profile` unverified → verification mail → verified badge |
| `login.spec.ts` | wrong password, log in → `/profile`, `return_to` honoured for an allowed origin and ignored for a foreign one, log out clears the session |
| `magic.spec.ts` | request a magic link → mail → `/magic?token=` logs in and verifies; a reused link fails |
| `profile.spec.ts` | edit name + handle, upload / remove the avatar (`/avatars/<id>` is WebP, then SVG), change the password revokes the other sessions |
| `session.spec.ts` | JWKS shape, `/session.js` headers, the widget on a host page served from another localhost origin (signed out / signed in) |

Pages are addressed by `data-testid` (`email`, `password`, `password-confirm`,
`password-current`, `toggle-password`, `handle`, `name`, `submit`, `magic-link`,
`provider-<name>`, `error`, `logout`, `logout-all`, `avatar-input`,
`avatar-remove`, `avatar-img`, `resend-verification`, `verified-badge`,
`session-row`, `save-profile`, `save-password`); keep them when touching the
web app.

`bun run test:critical` runs only the `@critical` tests; `bun run typecheck`
type-checks the suite without a running stack.
