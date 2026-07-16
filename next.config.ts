import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // All routes are static — export to ./out for Cloudflare Workers static assets.
  output: "export",
  // Production verification may run while `next dev` is serving the app. Keep
  // those compilers isolated so a build cannot replace the live dev-server cache.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // The demo is intentionally tested through both loopback hostnames.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
