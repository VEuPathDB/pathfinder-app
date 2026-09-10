import type { NextConfig } from "next";
import path from "path";

import { getConfiguredServerApiBaseUrl } from "./src/lib/config/apiBase";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  reactCompiler: true,
  // The dev-tools indicator button sits in a page corner and takes the pointer
  // events of the controls under it.
  devIndicators: false,
  output: "standalone",
  // Disable built-in gzip compression so SSE streams are flushed per-event
  // instead of being buffered by the compressor.  In production, the reverse
  // proxy (nginx / CDN) handles compression for non-streaming responses.
  compress: false,
  transpilePackages: ["@pathfinder/shared", "@veupathdb/assistant-client"],
  turbopack: {
    root: path.resolve(process.cwd(), "../.."),
  },
  experimental: {
    serverActions: {
      bodySizeLimit: "2mb",
    },
    // The API is reached through the `/api/:path*` rewrite below. Next's 30 s
    // default ends a slower call with its own bare 500, which hides the API's
    // answer; a purge that also deletes WDK strategies runs longer than that.
    proxyTimeout: 300_000,
  },
  async rewrites() {
    const apiBase = getConfiguredServerApiBaseUrl();
    return {
      afterFiles: [
        {
          source: "/health/:path*",
          destination: `${apiBase}/health/:path*`,
        },
        {
          source: "/api/:path*",
          destination: `${apiBase}/api/:path*`,
        },
        {
          source: "/docs",
          destination: `${apiBase}/docs`,
        },
        {
          source: "/docs/:path*",
          destination: `${apiBase}/docs/:path*`,
        },
        {
          source: "/redoc",
          destination: `${apiBase}/redoc`,
        },
        {
          source: "/redoc/:path*",
          destination: `${apiBase}/redoc/:path*`,
        },
        {
          source: "/openapi.json",
          destination: `${apiBase}/openapi.json`,
        },
      ],
    };
  },
};

export default nextConfig;
