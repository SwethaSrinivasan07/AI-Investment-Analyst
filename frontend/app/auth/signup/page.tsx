'use client'

import { useState, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { register, setToken } from '@/lib/api'

export default function SignupPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)

    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }

    setLoading(true)
    try {
      const data = await register(email, password)
      setToken(data.access_token)
      router.replace('/dashboard')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-[400px]">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2.5 mb-3">
            <div className="w-7 h-7 bg-[#2E2A47] flex items-center justify-center">
              <span className="text-white text-[10px] font-bold tracking-wider">AL</span>
            </div>
            <span className="font-serif text-[22px] text-[#121212]">AlphaLens</span>
          </div>
          <p className="text-[13px] text-[#5C5C5C]">Investment Research Platform</p>
        </div>

        <div className="bg-white border border-black/8 p-8">
          <h1 className="text-[15px] font-medium text-[#121212] mb-6">Create account</h1>

          {error && (
            <div className="mb-4 px-4 py-3 bg-[#A14A44]/8 border border-[#A14A44]/20 text-[#A14A44] text-[13px]">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-1.5">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3 py-2 bg-white border border-black/8 text-[#121212] placeholder-[#5C5C5C]/50 focus:outline-none focus:ring-1 focus:ring-[#2E2A47] focus:border-[#2E2A47] text-[13px] transition-colors"
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-1.5">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 bg-white border border-black/8 text-[#121212] placeholder-[#5C5C5C]/50 focus:outline-none focus:ring-1 focus:ring-[#2E2A47] focus:border-[#2E2A47] text-[13px] transition-colors"
                placeholder="Min. 8 characters"
              />
            </div>

            <div>
              <label htmlFor="confirm" className="block text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-1.5">
                Confirm Password
              </label>
              <input
                id="confirm"
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full px-3 py-2 bg-white border border-black/8 text-[#121212] placeholder-[#5C5C5C]/50 focus:outline-none focus:ring-1 focus:ring-[#2E2A47] focus:border-[#2E2A47] text-[13px] transition-colors"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 bg-[#2E2A47] hover:bg-[#1E1A35] disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium text-[13px] transition-colors flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Creating account...
                </>
              ) : (
                'Create account'
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-[13px] text-[#5C5C5C]">
            Already have an account?{' '}
            <Link href="/auth/login" className="text-[#2E2A47] font-medium hover:underline transition-colors">
              Sign in
            </Link>
          </p>
        </div>

        <p className="mt-6 text-center text-[11px] text-[#5C5C5C]/60">
          For educational use only. Not financial advice.
        </p>
      </div>
    </div>
  )
}
