import type { NextConfig } from "next";

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

if (process.env.VERCEL === "1") {
  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL must be configured for Vercel deployments.");
  }

  const { hostname, protocol } = new URL(apiUrl);
  const localHosts = new Set(["localhost", "127.0.0.1", "0.0.0.0", "::1"]);

  if (protocol !== "https:" || localHosts.has(hostname)) {
    throw new Error("NEXT_PUBLIC_API_URL must be a public HTTPS API origin for Vercel deployments.");
  }
}

const nextConfig: NextConfig = {};
export default nextConfig;
