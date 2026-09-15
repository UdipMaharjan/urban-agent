import type { NextConfig } from 'next';
const config: NextConfig = {
  distDir: process.env.URBANAGENT_TEST_BUILD_DIR || '.next',
  // Synchronous analysis batches can outlast Next's default proxy timeout.
  experimental: { proxyTimeout: 30 * 60 * 1000 },
  async rewrites() {
    const origin = process.env.BACKEND_API_URL || 'http://127.0.0.1:8000';
    return [{ source: '/backend/:path*', destination: `${origin}/:path*` }];
  },
};
export default config;
