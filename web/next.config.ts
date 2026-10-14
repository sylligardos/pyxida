import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  serverExternalPackages: ["better-sqlite3"],
  async rewrites() {
    return [
      // Needle, served as it is from game/web (public/play is a link to it).
      { source: "/play", destination: "/play/index.html" },
      { source: "/static/:path*", destination: "/play/:path*" },
      { source: "/api/stats", destination: "/api/game/stats" },
      { source: "/api/round/:path*", destination: "/api/game/round/:path*" },
    ];
  },
};

export default nextConfig;
