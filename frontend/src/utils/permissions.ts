// Central role → access rules. Keep in sync with backend auth.

import type { UserRole } from '../contexts/AuthContext'

// Roles restricted to a specific set of screens. Roles not listed here (master,
// viewer) can reach every non-master-only route.
const SCOPED_ROUTES: Partial<Record<UserRole, string[]>> = {
  planner: ['/indents', '/purchase-requests', '/consumption'],
  planner_view: ['/indents', '/purchase-requests', '/consumption'],
}

/** True if the role may view the given route path. */
export function canAccessRoute(role: UserRole | undefined, path: string): boolean {
  if (!role) return false
  const scoped = SCOPED_ROUTES[role]
  return scoped ? scoped.includes(path) : true
}

/** Where to send a user after login / when they hit a disallowed route. */
export function defaultRoute(role: UserRole | undefined): string {
  if (role && SCOPED_ROUTES[role]) return SCOPED_ROUTES[role]![0]
  return '/'
}

/** Roles allowed to generate indents. */
export function canGenerateIndent(role: UserRole | undefined): boolean {
  return role === 'master' || role === 'planner'
}

/** Roles allowed to create a Purchase Request. */
export function canCreatePR(role: UserRole | undefined): boolean {
  return role === 'master' || role === 'planner'
}

/** Full mutation rights (clear indents, add surge, manage masters/settings…). */
export function isManager(role: UserRole | undefined): boolean {
  return role === 'master'
}
