import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  serverExternalPackages: ["better-sqlite3"],
  async redirects() {
    // The three views that became Explore. Query strings (b, k) carry over.
    return ["landscape", "rankings", "redundancy"].map((v) => ({ source: `/${v}`, destination: `/explore?v=${v}`, permanent: false }));
  },
  async rewrites() {
    return [
      // Needle's screens, served as they are from public/play.
      { source: "/play", destination: "/play/index.html" },
      { source: "/static/:path*", destination: "/play/:path*" },
      { source: "/api/stats", destination: "/api/game/stats" },
      { source: "/api/round/:path*", destination: "/api/game/round/:path*" },
    ];
  },
};

export default nextConfig;
