/**
 * Standalone Node.js HTTP server entry (production).
 *
 * Built by `bun run build` into `server/entry.node-server.js` and started with
 * `node server/entry.node-server` (see Dockerfile CMD). Listens on 0.0.0.0:PORT
 * (PORT defaults to 3000), which Caddy reverse-proxies for metrics.3m4.net.
 */
import {
  createQwikCity,
  type PlatformNode,
} from "@builder.io/qwik-city/middleware/node";
import qwikCityPlan from "@qwik-city-plan";
import { manifest } from "@qwik-client-manifest";
import render from "./entry.ssr";
import { createServer } from "node:http";

declare global {
  // eslint-disable-next-line @typescript-eslint/no-empty-interface
  interface QwikCityPlatform extends PlatformNode {}
}

// Allow `staticFile` to serve built assets from /build and /assets.
const { router, notFound, staticFile } = createQwikCity({
  render,
  qwikCityPlan,
  manifest,
  static: {
    cacheControl: "public, max-age=31557600",
  },
});

const PORT = process.env.PORT ? parseInt(process.env.PORT, 10) : 3000;
const HOST = process.env.HOST ?? "0.0.0.0";

const server = createServer();

server.on("request", (req, res) => {
  staticFile(req, res, () => {
    router(req, res, () => {
      notFound(req, res, () => {});
    });
  });
});

server.listen(PORT, HOST, () => {
  // eslint-disable-next-line no-console
  console.log(`metrics web server listening on http://${HOST}:${PORT}/`);
});
