import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  serverExternalPackages: ["xlsx"],
  // The dev server is opened at 127.0.0.1. Without this, Next refuses the
  // module scripts that draw the charts.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
