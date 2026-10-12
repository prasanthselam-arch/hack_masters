import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, type ReactNode } from 'react'
import { ApiError, api, UNAUTHORIZED_EVENT } from './api'
import type { Account } from './types'

interface AuthCtx {
  account: Account | null
  loading: boolean
  error: unknown
  signedIn: (account: Account) => void
  signOut: () => Promise<void>
}

const Ctx = createContext<AuthCtx | null>(null)

async function fetchMe(): Promise<Account | null> {
  try {
    return await api.me()
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null
    throw e
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['me'], queryFn: fetchMe, staleTime: Infinity, retry: false })

  // Drop everything cached for the previous user (records, summaries, chat) on any account change.
  const reset = useCallback(
    (account: Account | null) => {
      // Keep the ['me'] query itself: clearing it would detach the observer above from the new value.
      qc.removeQueries({ predicate: (query) => query.queryKey[0] !== 'me' })
      sessionStorage.clear()
      qc.setQueryData(['me'], account)
    },
    [qc],
  )

  useEffect(() => {
    const expired = () => reset(null)
    window.addEventListener(UNAUTHORIZED_EVENT, expired)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, expired)
  }, [reset])

  const signOut = useCallback(async () => {
    await api.logout().catch(() => undefined)
    reset(null)
  }, [reset])

  return (
    <Ctx.Provider value={{ account: q.data ?? null, loading: q.isLoading, error: q.error, signedIn: reset, signOut }}>
      {children}
    </Ctx.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
