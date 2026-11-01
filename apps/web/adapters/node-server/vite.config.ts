import { nodeServerAdapter } from "@builder.io/qwik-city/adapters/node-server/vite";
import { extendConfig } from "@builder.io/qwik-city/vite";
import baseConfig from "../../vite.config";

/**
 * Server build config — produces server/entry.node-server.js,
 * a standalone Node HTTP server (used in Docker on port 3000).
 */
export default extendConfig(baseConfig, () => {
  return {
    build: {
      ssr: true,
      rollupOptions: {
        input: ["src/entry.node-server.tsx", "@qwik-city-plan"],
      },
    },
    plugins: [nodeServerAdapter({ name: "node-server" })],
  };
});
