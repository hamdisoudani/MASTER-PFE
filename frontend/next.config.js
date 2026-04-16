/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  transpilePackages: [
    '@blocknote/core',
    '@blocknote/react',
    '@blocknote/mantine',
    '@mantine/core',
    '@mantine/hooks',
  ],
  webpack: (config, { webpack }) => {
    // @copilotkit/react-core/v2 auto-imports a Tailwind v4 CSS file that
    // PostCSS cannot parse (PostCSSSyntaxError). We suppress that import so
    // the build succeeds. CopilotKit v2 styles can be added manually if needed.
    config.plugins.push(
      new webpack.IgnorePlugin({
        resourceRegExp: /index\.css$/,
        contextRegExp: /@copilotkit[\\/]react-core[\\/]dist[\\/]v2/,
      })
    );
    return config;
  },
};

module.exports = nextConfig;
