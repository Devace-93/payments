/**
 * Bundles the widget into a single minified IIFE (ES2019) and writes it to the
 * web app's public folder so the web service serves it at /session.js. Fails
 * the build when the gzipped output exceeds the contract budget (4 KB).
 */
import { gzipSync } from "node:zlib";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const root = resolve(import.meta.dir, "../..");
const output = resolve(root, "apps/web/public/session.js");
const BUDGET_GZ = 4 * 1024;

const result = await Bun.build({
  entrypoints: [resolve(import.meta.dir, "src/index.ts")],
  target: "browser",
  format: "iife",
  minify: true,
  sourcemap: "none",
  define: { "process.env.NODE_ENV": '"production"' },
});
if (!result.success) {
  for (const log of result.logs) console.error(log);
  process.exit(1);
}
const [artifact] = result.outputs;
const code = await artifact.text();
const banner = "/* 3m4 accounts session.js v0.1.0 — https://accounts.3m4.net — MIT */\n";
const out = banner + code;
const gz = gzipSync(Buffer.from(out)).length;
await mkdir(dirname(output), { recursive: true });
await writeFile(output, out);
console.log(`session.js: ${(out.length / 1024).toFixed(1)} KB raw, ${(gz / 1024).toFixed(2)} KB gzipped`);
if (gz > BUDGET_GZ) {
  console.error(`Over budget: ${gz} B gzipped > ${BUDGET_GZ} B`);
  process.exit(1);
}
