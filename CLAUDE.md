# accounts — notes for agents

- Spec: `CONTRACT.md` (session model, JWT claims, API, pages, widget, relying-app rules). Keep it in sync with the code.
- Sibling projects and reference implementations: `/home/enrique/metrics` and `/home/enrique/retro` (same stack and chrome; accounts was bootstrapped from them — retro has the mail sender and the outbox worker), `/home/enrique/3m4`, `/home/enrique/exp`. When in doubt, do what metrics does.
- Everything in this repo (code, comments, commits, docs) is written in English.
- Local stack: `make up` → http://localhost:8085 (8080 belongs to 3m4, 8081 to exp, 8082 to retro, 8083 to metrics). Compose project name `accounts`.
- Build mode: Claude writes the whole codebase unless Enrique says "modo aprender".
- Brand colour: Tailwind **indigo** (3m4 blue, exp violet, retro emerald, metrics cyan, bubbles orange).
- Security rules: passwords argon2id; refresh tokens and email tokens stored as sha256 only; never log tokens, passwords or raw IPs; same answer and timing for unknown email vs wrong password; a GET never consumes a token.
- This service has no product features: no plans, billing, API keys, MCP server or usage metering. Do not copy those from the template.
