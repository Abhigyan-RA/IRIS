import type { NextConfig } from 'next';

/**
 * Next.js configuration for the dashboard.
 *
 * The security headers below are set here because Next serves the dashboard
 * itself; the API sets its own equivalents. `poweredByHeader: false` removes the
 * default header that advertises the framework in use.
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  headers() {
    return Promise.resolve([
      {
        source: '/:path*',
        headers: [
          // Stop the browser from guessing a response's content type.
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          // Prevent other sites embedding the dashboard in a frame.
          { key: 'X-Frame-Options', value: 'DENY' },
          // Do not leak the current URL to sites the user navigates to.
          { key: 'Referrer-Policy', value: 'no-referrer' },
          // Isolate this page from other browsing contexts.
          { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
          // Turn off device APIs the dashboard never uses.
          {
            key: 'Permissions-Policy',
            value: 'geolocation=(), camera=(), microphone=()',
          },
        ],
      },
    ]);
  },
};

export default nextConfig;
