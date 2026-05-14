/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export for Cloudflare Pages hosting.
  // All API calls go to FastAPI — no Next.js server needed.
  output: 'export',
  images: {
    unoptimized: true, // required for static export
  },
}

export default nextConfig
