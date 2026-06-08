import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import type { ReactNode } from 'react'

interface Props {
  children: ReactNode
  /** If true, only 'master' role can access; viewers get 403 page */
  masterOnly?: boolean
}

export default function ProtectedRoute({ children, masterOnly = false }: Props) {
  const { user } = useAuth()
  const location = useLocation()

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (masterOnly && user.role !== 'master') {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4" style={{ color: 'var(--c-text-sub)' }}>
        <span style={{ fontSize: '3rem' }}>🔒</span>
        <p className="text-lg font-semibold" style={{ color: 'var(--c-text)' }}>Access Denied</p>
        <p className="text-sm">This page requires the <strong>Master</strong> role.</p>
      </div>
    )
  }

  return <>{children}</>
}
