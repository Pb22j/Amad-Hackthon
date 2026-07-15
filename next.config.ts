import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // All routes are static — export to ./out for Cloudflare Workers static assets.
  output: "export",
};

export default nextConfig;
