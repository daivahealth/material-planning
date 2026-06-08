import { useState, useEffect } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import {
  LayoutDashboard, Building2, Store, Package, Truck, Settings,
  UploadCloud, ClipboardList, BarChart2, TrendingUp, Clock, Palette, DatabaseZap, Activity
} from 'lucide-react'

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

export default function Layout() {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem('medplan-theme') as Theme) ?? 'cyber'
  )

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('medplan-theme', theme)
  }, [theme])

  const cycleTheme = () => {
    const idx = THEMES.findIndex(t => t.id === theme)
    const next = THEMES[(idx + 1) % THEMES.length]
    setTheme(next.id)
  }
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
        </nav>

        {/* Footer */}
        <div
          className="px-4 py-3 flex items-center justify-between"
          style={{ borderTop: '1px solid rgba(var(--c-accent-rgb), 0.08)' }}
        >
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
      </aside>

      {/* Main content */}
      <main
        className="flex-1 overflow-y-auto p-6"
        style={{ background: 'transparent' }}
      >
        <Outlet />
      </main>
    </div>
  )
}
