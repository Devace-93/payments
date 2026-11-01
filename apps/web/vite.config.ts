import { defineConfig } from "vite";
import { qwikVite } from "@builder.io/qwik/optimizer";
import { qwikCity } from "@builder.io/qwik-city/vite";
import { fileURLToPath } from "node:url";

/**
 * Base Vite config (client build + dev server).
 * The node-server adapter extends this in adapters/node-server/vite.config.ts.
 */
export default defineConfig(() => {
  return {
    resolve: {
      alias: {
        "~": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    plugins: [qwikCity(), qwikVite()],
    // Allow importing packages/shared/*.json from the monorepo root in dev.
    server: {
      fs: {
        allow: [".", "../../packages"],
      },
    },
    preview: {
      headers: {
        "Cache-Control": "public, max-age=600",
      },
    },
  };
});
