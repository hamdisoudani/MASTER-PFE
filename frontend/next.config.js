/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [{
      source: '/api/copilotkit/:path*',
      destination: `${process.env.NEXT_PUBLIC_COPILOTKIT_RUNTIME_URL ?? 'http://localhost:3001/copilotkit'}/:path*`,
    }];
  },
};
module.exports = nextConfig;
