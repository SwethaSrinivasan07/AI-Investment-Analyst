// Server component wrapper — required for static export with dynamic routes.
// generateStaticParams must live in a server component, not a 'use client' file.
// Returns [] because memo IDs only exist at runtime; the Cloudflare Pages
// _redirects SPA fallback handles direct URL loads and page refreshes.
import MemoPageClient from './MemoPageClient'

export function generateStaticParams() {
  return []
}

export default function MemoPage() {
  return <MemoPageClient />
}
