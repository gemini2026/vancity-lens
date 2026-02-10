import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* Required for mapbox-gl CSS import */
  output: "standalone", // Optimized for Docker / Cloudflare Pages
  reactStrictMode: false, // mapbox-gl v3 breaks with strict mode double-mount in dev
};

export default nextConfig;
