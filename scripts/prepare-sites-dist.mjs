import { cp, mkdir, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = process.cwd();
const exportedSite = resolve(root, "out");
const dist = resolve(root, "dist");

await rm(dist, { recursive: true, force: true });
await mkdir(resolve(dist, "server"), { recursive: true });
await cp(exportedSite, resolve(dist, "client"), { recursive: true });

// Sites expects a Cloudflare Worker-compatible entry point. Next.js has
// already exported every route as a static asset, so the worker delegates all
// requests to the platform's asset binding.
await writeFile(
  resolve(dist, "server", "index.js"),
  `export default {
  async fetch(request, env) {
    return env.ASSETS.fetch(request);
  },
};
`,
  "utf8",
);
