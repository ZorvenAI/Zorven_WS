import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output for Docker deployment
  output: "standalone",

  // Optimize images
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
    ],
  },

  // Enable strict mode for better error catching
  reactStrictMode: true,

  // Disable x-powered-by header for security
  poweredByHeader: false,

  // Configure environment variables exposed to the browser
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
};

export default nextConfig;

// rebuild trigger
