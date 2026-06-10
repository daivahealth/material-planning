import { useState, type FormEvent } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { Lock, User } from 'lucide-react'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: Location })?.from?.pathname ?? '/'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(username, password)
      navigate(from, { replace: true })
    } catch {
      setError('Invalid username or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: 'var(--c-bg)' }}
    >
      {/* Subtle grid overlay */}
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          backgroundImage: `linear-gradient(var(--c-grid-color) 1px, transparent 1px),
            linear-gradient(90deg, var(--c-grid-color) 1px, transparent 1px)`,
          backgroundSize: '40px 40px',
        }}
      />

      <div
        className="relative z-10 w-full max-w-sm mx-4 p-8 rounded-xl"
        style={{
          background: 'linear-gradient(135deg, var(--c-modal-from), var(--c-modal-to))',
          border: '1px solid var(--c-border)',
          boxShadow: '0 0 40px rgba(0,0,0,0.5), 0 0 80px rgba(var(--c-accent-rgb), 0.06)',
        }}
      >
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-2">
            <div
              className="w-3 h-3 rounded-full"
              style={{ background: 'var(--c-cyan)', boxShadow: '0 0 10px var(--c-cyan)' }}
            />
            <span
              className="text-xl font-bold tracking-widest uppercase"
              style={{
                background: 'linear-gradient(90deg, var(--c-cyan), var(--c-purple))',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              MedPlan
            </span>
          </div>
          <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>
            Material Planning System
          </p>
        </div>

        <h1
          className="text-center text-lg font-semibold mb-6"
          style={{ color: 'var(--c-text)' }}
        >
          Sign in to continue
        </h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Username */}
          <div>
            <label className="block text-xs mb-1 font-medium" style={{ color: 'var(--c-text-sub)' }}>
              Username
            </label>
            <div className="relative">
              <User
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
                style={{ color: 'var(--c-text-sub)' }}
              />
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                required
                autoFocus
                autoComplete="username"
                className="w-full pl-9 pr-3 py-2.5 rounded-lg text-sm outline-none transition-all"
                style={{
                  background: 'rgba(var(--c-accent-rgb), 0.04)',
                  border: '1px solid var(--c-border)',
                  color: 'var(--c-text)',
                }}
                onFocus={e => (e.currentTarget.style.borderColor = 'rgba(var(--c-accent-rgb), 0.5)')}
                onBlur={e => (e.currentTarget.style.borderColor = 'var(--c-border)')}
                placeholder="admin"
              />
            </div>
          </div>

          {/* Password */}
          <div>
            <label className="block text-xs mb-1 font-medium" style={{ color: 'var(--c-text-sub)' }}>
              Password
            </label>
            <div className="relative">
              <Lock
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
                style={{ color: 'var(--c-text-sub)' }}
              />
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="w-full pl-9 pr-3 py-2.5 rounded-lg text-sm outline-none transition-all"
                style={{
                  background: 'rgba(var(--c-accent-rgb), 0.04)',
                  border: '1px solid var(--c-border)',
                  color: 'var(--c-text)',
                }}
                onFocus={e => (e.currentTarget.style.borderColor = 'rgba(var(--c-accent-rgb), 0.5)')}
                onBlur={e => (e.currentTarget.style.borderColor = 'var(--c-border)')}
                placeholder="••••••••"
              />
            </div>
          </div>

          {error && (
            <p
              className="text-xs rounded-lg px-3 py-2"
              style={{
                color: 'var(--c-red)',
                background: 'rgba(255,37,96,0.08)',
                border: '1px solid rgba(255,37,96,0.2)',
              }}
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-lg text-sm font-semibold transition-all"
            style={{
              background: loading
                ? 'rgba(var(--c-accent-rgb), 0.3)'
                : 'linear-gradient(135deg, var(--c-cyan), rgba(var(--c-accent-rgb), 0.8))',
              color: 'var(--c-bg)',
              border: 'none',
              cursor: loading ? 'not-allowed' : 'pointer',
              boxShadow: loading ? 'none' : '0 0 15px rgba(var(--c-accent-rgb), 0.3)',
            }}
          >
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
