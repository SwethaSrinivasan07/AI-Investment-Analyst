'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { hasToken } from '@/lib/api'

export default function Home() {
  const router = useRouter()

  useEffect(() => {
    if (hasToken()) {
      router.replace('/dashboard')
    } else {
      router.replace('/auth/login')
    }
  }, [router])

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}
