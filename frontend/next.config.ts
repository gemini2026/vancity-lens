import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* Required for mapbox-gl CSS import */
  output: "standalone", // Optimized for Docker / Cloudflare Pages
};

export default nextConfig;
