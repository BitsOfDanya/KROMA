import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  agentRules: false,
  async rewrites() {
    const backend = process.env.KROMA_BACKEND_URL ?? "http://127.0.0.1:8000";
    return ["/api/:path*", "/docs", "/openapi.json", "/health", "/models"].map(
      (source) => ({ source, destination: `${backend}${source}` }),
    );
  },
  output: "standalone",
};

export default nextConfig;
