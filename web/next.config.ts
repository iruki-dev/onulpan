import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 자체 호스팅: `node .next/standalone/server.js`로 띄운다 (infra/systemd/onulpan-web.service)
  output: "standalone",
  serverExternalPackages: ["pg", "@resvg/resvg-js"],
  poweredByHeader: false,
};

export default nextConfig;
