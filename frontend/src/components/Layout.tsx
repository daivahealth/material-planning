import { useState, useEffect } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Building2, Store, Package, Truck, Settings,
  UploadCloud, ClipboardList, BarChart2, TrendingUp, Clock, Palette, DatabaseZap, Activity,
  Users, LogOut, ShieldCheck, Eye, KeyRound, X, Check,
} from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import { useAuth } from '../contexts/AuthContext'
import { resetMyPassword } from '../api/client'
import { PasswordStrength, isPasswordValid } from './PasswordStrength'

type Theme = 'cyber' | 'ember' | 'swagger'

const THEMES: { id: Theme; label: string; accent: string }[] = [
  { id: 'cyber', label: 'Cyber', accent: '#00d4ff' },
  { id: 'ember', label: 'Ember', accent: '#fbbf24' },
  { id: 'swagger', label: 'Swagger', accent: '#49cc90' },
]

const nav = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/hospitals', label: 'Hospitals', icon: Building2 },
  { to: '/stores', label: 'Stores', icon: Store },
  { to: '/items', label: 'Items', icon: Package },
  { to: '/suppliers', label: 'Suppliers', icon: Truck },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/imports', label: 'CSV Import', icon: UploadCloud },
  { to: '/indents', label: 'Indent Planning', icon: ClipboardList },
  { to: '/surges', label: 'Surge Records', icon: TrendingUp },
  { to: '/classification', label: 'FSN / VED', icon: BarChart2 },
  { to: '/consumption', label: 'Consumption', icon: Activity },
  { to: '/scheduler', label: 'Scheduler', icon: Clock },
  { to: '/data-mining', label: 'Data Mining', icon: DatabaseZap },
]

interface ResetForm {
  current: string
  next: string
  confirm: string
}

export default function Layout() {
  const { user, logout, isMaster } = useAuth()
  const navigate = useNavigate()
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem('medplan-theme') as Theme) ?? 'cyber'
  )
  const [showReset, setShowReset] = useState(false)
  const [form, setForm] = useState<ResetForm>({ current: '', next: '', confirm: '' })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('medplan-theme', theme)
  }, [theme])

  const cycleTheme = () => {
    const idx = THEMES.findIndex(t => t.id === theme)
    const next = THEMES[(idx + 1) % THEMES.length]
    setTheme(next.id)
  }

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const openReset = () => {
    setForm({ current: '', next: '', confirm: '' })
    setShowReset(true)
  }

  const resetMut = useMutation({
    mutationFn: () => resetMyPassword(form.current, form.next),
    onSuccess: () => setShowReset(false),
  })

  const canSubmit =
    form.current.length > 0 &&
    isPasswordValid(form.next) &&
    form.next === form.confirm &&
    !resetMut.isPending

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside
        className="w-60 flex flex-col flex-shrink-0"
        style={{
          background: 'linear-gradient(180deg, var(--c-sidebar-from) 0%, var(--c-sidebar-to) 100%)',
          borderRight: '1px solid var(--c-sidebar-bdr)',
        }}
      >
        {/* Logo */}
        <div
          className="px-5 py-5"
          style={{ borderBottom: '1px solid rgba(var(--c-accent-rgb), 0.1)' }}
        >
          <div className="flex items-center gap-2 mb-0.5">
            <div
              className="w-2 h-2 rounded-full"
              style={{
                background: 'var(--c-cyan)',
                boxShadow: '0 0 6px var(--c-cyan)',
              }}
            />
            <span
              className="text-xs font-bold tracking-widest uppercase"
              style={{
                background: 'linear-gradient(90deg, var(--c-cyan), var(--c-purple))',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              MedPlan
            </span>
          </div>
          <p className="text-xs pl-4" style={{ color: 'var(--c-text-sub)' }}>
            Material Planning System
          </p>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-3 px-2">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                isActive ? 'nav-item-active' : 'nav-item'
              }
              style={({ isActive }) => isActive ? {
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.45rem 0.75rem',
                borderRadius: '0.375rem',
                marginBottom: '0.125rem',
                fontSize: '0.8125rem',
                fontWeight: 500,
                color: 'var(--c-cyan)',
                background: 'rgba(var(--c-accent-rgb), 0.08)',
                border: '1px solid rgba(var(--c-accent-rgb), 0.18)',
                boxShadow: '0 0 8px rgba(var(--c-accent-rgb), 0.1)',
                textDecoration: 'none',
              } : {
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.45rem 0.75rem',
                borderRadius: '0.375rem',
                marginBottom: '0.125rem',
                fontSize: '0.8125rem',
                color: 'var(--c-text-sub)',
                border: '1px solid transparent',
                textDecoration: 'none',
                transition: 'all 0.15s',
              }}
            >
              <Icon size={14} />
              {label}
            </NavLink>
          ))}

          {/* Users link — master only */}
          {isMaster && (
            <NavLink
              to="/users"
              className={({ isActive }) => isActive ? 'nav-item-active' : 'nav-item'}
              style={({ isActive }) => isActive ? {
                display: 'flex', alignItems: 'center', gap: '0.5rem',
                padding: '0.45rem 0.75rem', borderRadius: '0.375rem', marginBottom: '0.125rem',
                fontSize: '0.8125rem', fontWeight: 500, color: 'var(--c-cyan)',
                background: 'rgba(var(--c-accent-rgb), 0.08)',
                border: '1px solid rgba(var(--c-accent-rgb), 0.18)',
                boxShadow: '0 0 8px rgba(var(--c-accent-rgb), 0.1)', textDecoration: 'none',
              } : {
                display: 'flex', alignItems: 'center', gap: '0.5rem',
                padding: '0.45rem 0.75rem', borderRadius: '0.375rem', marginBottom: '0.125rem',
                fontSize: '0.8125rem', color: 'var(--c-text-sub)',
                border: '1px solid transparent', textDecoration: 'none', transition: 'all 0.15s',
              }}
            >
              <Users size={14} /> Users
            </NavLink>
          )}
        </nav>

        {/* Footer — user info + controls */}
        <div
          className="px-3 py-3 space-y-2"
          style={{ borderTop: '1px solid rgba(var(--c-accent-rgb), 0.08)' }}
        >
          {/* Logged-in user */}
          {user && (
            <div
              className="flex items-center gap-2 px-2 py-1.5 rounded-lg"
              style={{ background: 'rgba(var(--c-accent-rgb), 0.04)', border: '1px solid rgba(var(--c-accent-rgb), 0.08)' }}
            >
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold"
                style={{ background: 'rgba(var(--c-accent-rgb), 0.15)', color: 'var(--c-cyan)' }}
              >
                {user.username[0].toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium truncate" style={{ color: 'var(--c-text)' }}>{user.username}</p>
                <div className="flex items-center gap-1">
                  {user.role === 'master'
                    ? <ShieldCheck size={9} style={{ color: 'var(--c-cyan)' }} />
                    : <Eye size={9} style={{ color: 'var(--c-text-sub)' }} />
                  }
                  <span className="text-xs capitalize" style={{ color: 'var(--c-text-sub)' }}>{user.role}</span>
                </div>
              </div>
              {/* Change password */}
              <button
                title="Change my password"
                onClick={openReset}
                className="p-1 rounded transition-colors flex-shrink-0"
                style={{ color: 'var(--c-text-sub)' }}
                onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-purple)')}
                onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-sub)')}
              >
                <KeyRound size={12} />
              </button>
              {/* Sign out */}
              <button
                title="Sign out"
                onClick={handleLogout}
                className="p-1 rounded transition-colors flex-shrink-0"
                style={{ color: 'var(--c-text-sub)' }}
                onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-red)')}
                onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-sub)')}
              >
                <LogOut size={12} />
              </button>
            </div>
          )}

          {/* Version + theme */}
          <div className="flex items-center justify-between px-1">
            <span className="text-xs" style={{ color: 'var(--c-text-sub)' }}>v2.0 · 2026</span>
            <button
              onClick={cycleTheme}
              title={`Theme: ${THEMES.find(t => t.id === theme)?.label} — click to switch`}
              className="flex items-center gap-1.5 text-xs transition-colors"
              style={{ color: 'var(--c-text-sub)' }}
              onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-cyan)')}
              onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-sub)')}
            >
              <span
                className="w-2 h-2 rounded-full inline-block"
                style={{ background: THEMES.find(t => t.id === theme)?.accent, boxShadow: `0 0 5px ${THEMES.find(t => t.id === theme)?.accent}` }}
              />
              <Palette size={13} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main
        className="flex-1 overflow-y-auto p-6"
        style={{ background: 'transparent' }}
      >
        <Outlet />
      </main>

      {/* ── Change My Password Modal ── */}
      {showReset && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.6)' }}
        >
          <div
            className="w-full max-w-sm rounded-xl p-6"
            style={{
              background: 'linear-gradient(135deg, var(--c-modal-from), var(--c-modal-to))',
              border: '1px solid var(--c-border)',
              boxShadow: '0 0 40px rgba(0,0,0,0.6)',
            }}
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2">
                <KeyRound size={15} style={{ color: 'var(--c-purple)' }} />
                <h2 className="font-semibold text-base" style={{ color: 'var(--c-text)' }}>
                  Change My Password
                </h2>
              </div>
              <button
                onClick={() => setShowReset(false)}
                style={{ color: 'var(--c-text-sub)' }}
                onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-text)')}
                onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-sub)')}
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-4">
              {/* Current password */}
              <div>
                <label className="block text-xs mb-1 font-medium" style={{ color: 'var(--c-text-sub)' }}>
                  Current Password
                </label>
                <input
                  className="cyber-input"
                  type="password"
                  value={form.current}
                  onChange={e => setForm(f => ({ ...f, current: e.target.value }))}
                  placeholder="Enter current password"
                  autoFocus
                />
              </div>

              {/* New password */}
              <div>
                <label className="block text-xs mb-1 font-medium" style={{ color: 'var(--c-text-sub)' }}>
                  New Password
                </label>
                <input
                  className="cyber-input"
                  type="password"
                  value={form.next}
                  onChange={e => setForm(f => ({ ...f, next: e.target.value }))}
                  placeholder="Enter new password"
                />
                <PasswordStrength password={form.next} />
              </div>

              {/* Confirm new password */}
              <div>
                <label className="block text-xs mb-1 font-medium" style={{ color: 'var(--c-text-sub)' }}>
                  Confirm New Password
                </label>
                <input
                  className="cyber-input"
                  type="password"
                  value={form.confirm}
                  onChange={e => setForm(f => ({ ...f, confirm: e.target.value }))}
                  placeholder="Re-enter new password"
                />
                {form.confirm && form.next !== form.confirm && (
                  <p className="mt-1 text-xs" style={{ color: 'var(--c-red)' }}>
                    Passwords do not match
                  </p>
                )}
                {form.confirm && form.next === form.confirm && isPasswordValid(form.next) && (
                  <p className="mt-1 text-xs flex items-center gap-1" style={{ color: 'var(--c-green)' }}>
                    <Check size={10} strokeWidth={3} /> Passwords match
                  </p>
                )}
              </div>

              {/* Server error */}
              {resetMut.isError && (
                <p className="text-xs" style={{ color: 'var(--c-red)' }}>
                  {(resetMut.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
                    ?? 'Failed to update password'}
                </p>
              )}

              {/* Actions */}
              <div className="flex justify-end gap-2 pt-1">
                <button className="btn-secondary" onClick={() => setShowReset(false)}>
                  Cancel
                </button>
                <button
                  className="btn-primary flex items-center gap-1"
                  disabled={!canSubmit}
                  onClick={() => resetMut.mutate()}
                >
                  <KeyRound size={13} /> Update Password
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
