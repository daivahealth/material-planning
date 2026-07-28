import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export type UserRole = 'master' | 'viewer' | 'planner' | 'planner_view'

export interface AuthUser {
  id: number
  username: string
  email: string | null
  role: UserRole
  is_active: boolean
}

interface AuthContextValue {
  user: AuthUser | null
  token: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  isMaster: boolean
  /** Password rotation: true when the password must be changed before use. */
  passwordExpired: boolean
  /** Days until expiry (negative = overdue); null when rotation is disabled. */
  passwordExpiresInDays: number | null
  /** Called after a successful self-service change. */
  clearPasswordExpiry: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

const TOKEN_KEY = 'medplan_token'
const USER_KEY = 'medplan_user'
const PWD_EXPIRED_KEY = 'medplan_pwd_expired'
const PWD_DAYS_KEY = 'medplan_pwd_days'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [passwordExpired, setPasswordExpired] = useState<boolean>(
    () => localStorage.getItem(PWD_EXPIRED_KEY) === '1')
  const [passwordExpiresInDays, setPasswordExpiresInDays] = useState<number | null>(() => {
    const raw = localStorage.getItem(PWD_DAYS_KEY)
    return raw === null || raw === '' ? null : Number(raw)
  })
  const [user, setUser] = useState<AuthUser | null>(() => {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as AuthUser) : null
  })

  // Sync token into axios default headers whenever it changes
  useEffect(() => {
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`
    } else {
      delete api.defaults.headers.common['Authorization']
    }
  }, [token])

  const login = async (username: string, password: string) => {
    const form = new URLSearchParams()
    form.append('username', username)
    form.append('password', password)
    const { data } = await api.post<{
      access_token: string; user: AuthUser
      password_expired?: boolean; password_expires_in_days?: number | null
    }>(
      '/api/auth/login',
      form,
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
    )
    // Drop any cached query data from a previous session before switching user,
    // so a new user never sees the prior user's (differently-scoped) data.
    queryClient.clear()
    localStorage.setItem(TOKEN_KEY, data.access_token)
    localStorage.setItem(USER_KEY, JSON.stringify(data.user))
    const expired = !!data.password_expired
    const days = data.password_expires_in_days ?? null
    localStorage.setItem(PWD_EXPIRED_KEY, expired ? '1' : '0')
    localStorage.setItem(PWD_DAYS_KEY, days === null ? '' : String(days))
    setToken(data.access_token)
    setUser(data.user)
    setPasswordExpired(expired)
    setPasswordExpiresInDays(days)
  }

  const clearPasswordExpiry = () => {
    localStorage.setItem(PWD_EXPIRED_KEY, '0')
    localStorage.removeItem(PWD_DAYS_KEY)
    setPasswordExpired(false)
    setPasswordExpiresInDays(null)
    // Every query issued while the password was expired came back 403 and is
    // cached as empty. Refetch them so the UI fills in without a manual reload.
    queryClient.invalidateQueries()
  }

  const logout = () => {
    queryClient.clear()
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem(PWD_EXPIRED_KEY)
    localStorage.removeItem(PWD_DAYS_KEY)
    setToken(null)
    setUser(null)
    setPasswordExpired(false)
    setPasswordExpiresInDays(null)
  }

  return (
    <AuthContext.Provider value={{ user, token, login, logout, isMaster: user?.role === 'master',
               passwordExpired, passwordExpiresInDays, clearPasswordExpiry }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
