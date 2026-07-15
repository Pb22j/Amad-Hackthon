import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // All routes are static — export to ./out for Cloudflare Workers static assets.
  output: "export",
  // The demo is intentionally tested through both loopback hostnames.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
