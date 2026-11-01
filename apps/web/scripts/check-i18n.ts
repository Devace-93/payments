/**
 * Catalog integrity check: every base-language catalog must contain every
 * English key, nothing extra, no empty strings, and the same `{placeholders}`
 * per key. Country variants may contain any subset. Also verifies that every
 * locale in LANGS has a base catalog.
 *
 *   bun run check:i18n
 */
import { readdirSync } from "node:fs";
import { join } from "node:path";
import en from "../src/i18n/catalog/en";
import { LANGS } from "../src/i18n/langs";

const dir = join(import.meta.dir, "..", "src", "i18n", "catalog");
const files = readdirSync(dir).filter((f) => f.endsWith(".ts") && f !== "en.ts");
const enKeys = Object.keys(en);
const placeholderRe = /\{[a-zA-Z]+\}/g;
let ok = true;

const bases = new Set(files.filter((f) => !f.includes("-")).map((f) => f.replace(".ts", "")));
for (const l of LANGS) {
  const base = l.code.slice(0, 2);
  if (base !== "en" && !bases.has(base)) {
    ok = false;
    console.log(`${l.code}: no base catalog ${base}.ts`);
  }
}

for (const file of files.sort()) {
  const name = file.replace(".ts", "");
  const variant = name.includes("-");
  const cat: Record<string, string> = (await import(join(dir, file))).default;
  const keys = Object.keys(cat);
  const missing = variant ? [] : enKeys.filter((k) => !(k in cat));
  const extra = keys.filter((k) => !(k in en));
  const badPlaceholders: string[] = [];
  const empty: string[] = [];
  for (const k of keys) {
    const v = cat[k];
    if (typeof v !== "string" || !v.trim()) empty.push(k);
    const want = ((en as Record<string, string>)[k]?.match(placeholderRe) ?? []).sort().join(",");
    const got = (String(v).match(placeholderRe) ?? []).sort().join(",");
    if (k in en && want !== got) badPlaceholders.push(`${k} (en: ${want || "-"}, ${name}: ${got || "-"})`);
  }
  const bad = missing.length || extra.length || badPlaceholders.length || empty.length;
  if (bad) ok = false;
  console.log(`${name.padEnd(6)} ${String(keys.length).padStart(3)} keys${variant ? " (variant)" : ""}${bad ? "  ✘" : ""}`);
  if (missing.length) console.log("  missing:", missing);
  if (extra.length) console.log("  extra:", extra);
  if (badPlaceholders.length) console.log("  placeholders:", badPlaceholders);
  if (empty.length) console.log("  empty:", empty);
}
console.log(ok ? `OK — ${files.length} catalogs, ${enKeys.length} keys` : "FAILED");
process.exit(ok ? 0 : 1);
