import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getUsers, createUser, updateUser, deleteUser, changePassword, unlockUser, getHospitals, getStores } from '../api/client'
import PageHeader from '../components/PageHeader'
import { PasswordStrength, isPasswordValid } from '../components/PasswordStrength'
import { useAuth } from '../contexts/AuthContext'
import { Plus, Pencil, Trash2, KeyRound, ShieldCheck, Eye, X, Check, Search, ChevronRight, ChevronDown, Building2, Lock, Unlock } from 'lucide-react'

type Role = 'master' | 'viewer' | 'planner' | 'planner_view'

const ROLE_LABELS: Record<Role, string> = {
  master: 'Master',
  viewer: 'Viewer',
  planner: 'Planner',
  planner_view: 'Planner View',
}

const SCOPED_ROLES: Role[] = ['planner', 'planner_view']
const isScopedRole = (r: Role) => SCOPED_ROLES.includes(r)

interface UserRow {
  id: number
  username: string
  email: string | null
  role: Role
  is_active: boolean
  created_at: string
  updated_at: string
  failed_login_attempts: number
  locked_at: string | null
  hospital_ids: number[]
  store_ids: number[]
}

interface UserFormState {
  username: string
  email: string
  password: string
  role: Role
  hospital_ids: number[]
  store_ids: number[]
}

interface EditFormState {
  email: string
  role: Role
  is_active: boolean
  hospital_ids: number[]
  store_ids: number[]
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function Users() {
  const { user: me } = useAuth()
  const qc = useQueryClient()
  const { data: users = [], isLoading } = useQuery<UserRow[]>({
    queryKey: ['users'],
    queryFn: getUsers,
  })
  // Master is viewing this page, so these return the full, unscoped lists.
  const { data: hospitals = [] } = useQuery({ queryKey: ['hospitals'], queryFn: getHospitals })
  const { data: stores = [] } = useQuery({ queryKey: ['stores'], queryFn: () => getStores() })

  const [showCreate, setShowCreate] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [pwdId, setPwdId] = useState<number | null>(null)
  const [newPwd, setNewPwd] = useState('')
  const [createForm, setCreateForm] = useState<UserFormState>({
    username: '', email: '', password: '', role: 'viewer', hospital_ids: [], store_ids: [],
  })
  const [editForm, setEditForm] = useState<EditFormState>({ email: '', role: 'viewer', is_active: true, hospital_ids: [], store_ids: [] })

  const refetch = () => qc.invalidateQueries({ queryKey: ['users'] })

  const createMut = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      setShowCreate(false)
      setCreateForm({ username: '', email: '', password: '', role: 'viewer', hospital_ids: [], store_ids: [] })
      refetch()
    },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<EditFormState> }) => updateUser(id, data),
    onSuccess: () => { setEditId(null); refetch() },
  })

  const deleteMut = useMutation({
    mutationFn: deleteUser,
    onSuccess: refetch,
  })

  const unlockMut = useMutation({
    mutationFn: unlockUser,
    onSuccess: refetch,
  })

  const pwdMut = useMutation({
    mutationFn: ({ id, password }: { id: number; password: string }) => changePassword(id, password),
    onSuccess: () => { setPwdId(null); setNewPwd('') },
  })

  const startEdit = (u: UserRow) => {
    setEditId(u.id)
    setEditForm({
      email: u.email ?? '', role: u.role, is_active: u.is_active,
      hospital_ids: u.hospital_ids ?? [], store_ids: u.store_ids ?? [],
    })
  }

  const roleBadge = (role: Role) => (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold"
      style={role === 'master' ? {
        background: 'rgba(var(--c-accent-rgb), 0.12)',
        color: 'var(--c-cyan)',
        border: '1px solid rgba(var(--c-accent-rgb), 0.25)',
      } : {
        background: 'rgba(90,120,152,0.12)',
        color: 'var(--c-text-sub)',
        border: '1px solid rgba(90,120,152,0.2)',
      }}
    >
      {role === 'master' ? <ShieldCheck size={10} /> : <Eye size={10} />}
      {ROLE_LABELS[role] ?? role}
    </span>
  )

  return (
    <div>
      <PageHeader title="User Management">Manage system users and their access roles</PageHeader>

      <div className="flex justify-end mb-4">
        <button className="btn-primary flex items-center gap-1.5" onClick={() => setShowCreate(true)}>
          <Plus size={14} /> New User
        </button>
      </div>

      <div className="cyber-panel">
        {isLoading ? (
          <p className="p-4 text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="cyber-th">Username</th>
                <th className="cyber-th">Email</th>
                <th className="cyber-th">Role</th>
                <th className="cyber-th">Status</th>
                <th className="cyber-th">Created</th>
                <th className="cyber-th">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id} className="cyber-tr">
                  <td className="px-4 py-2 font-mono font-medium" style={{ color: 'var(--c-text)' }}>
                    {u.username}
                    {u.id === me?.id && (
                      <span className="ml-2 text-xs" style={{ color: 'var(--c-text-sub)' }}>(you)</span>
                    )}
                  </td>
                  <td className="px-4 py-2" style={{ color: 'var(--c-text-sub)' }}>{u.email || '—'}</td>
                  <td className="px-4 py-2">{roleBadge(u.role)}</td>
                  <td className="px-4 py-2">
                    <span className={`text-xs font-semibold ${u.is_active ? '' : 'opacity-50'}`}
                      style={{ color: u.is_active ? 'var(--c-green)' : 'var(--c-red)' }}>
                      {u.is_active ? 'Active' : 'Inactive'}
                    </span>
                    {u.locked_at && (
                      <span className="ml-2 inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-semibold"
                        title={`Locked after ${u.failed_login_attempts} failed sign-in attempts on ${new Date(u.locked_at).toLocaleString()}`}
                        style={{ background: 'rgba(255,77,77,0.12)', color: 'var(--c-red)', border: '1px solid rgba(255,77,77,0.3)' }}>
                        <Lock size={9} /> Locked
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs" style={{ color: 'var(--c-text-sub)' }}>
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-1">
                      <button
                        title="Edit"
                        className="p-1.5 rounded transition-colors"
                        style={{ color: 'var(--c-text-sub)' }}
                        onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-cyan)')}
                        onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-sub)')}
                        onClick={() => startEdit(u)}
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        title="Change password"
                        className="p-1.5 rounded transition-colors"
                        style={{ color: 'var(--c-text-sub)' }}
                        onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-purple)')}
                        onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-sub)')}
                        onClick={() => { setPwdId(u.id); setNewPwd('') }}
                      >
                        <KeyRound size={13} />
                      </button>
                      {u.locked_at && (
                        <button
                          title="Unlock account"
                          className="p-1.5 rounded transition-colors"
                          style={{ color: 'var(--c-red)' }}
                          disabled={unlockMut.isPending}
                          onClick={() => unlockMut.mutate(u.id)}
                        >
                          <Unlock size={13} />
                        </button>
                      )}
                      {u.id !== me?.id && (
                        <button
                          title="Delete"
                          className="p-1.5 rounded transition-colors"
                          style={{ color: 'var(--c-text-sub)' }}
                          onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-red)')}
                          onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-sub)')}
                          onClick={() => { if (confirm(`Delete user "${u.username}"?`)) deleteMut.mutate(u.id) }}
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Create Modal ── */}
      {showCreate && (
        <Modal title="Create User" onClose={() => setShowCreate(false)}>
          <div className="space-y-3">
            <Field label="Username">
              <input className="cyber-input" value={createForm.username}
                onChange={e => setCreateForm(f => ({ ...f, username: e.target.value }))} />
            </Field>
            <Field label="Email (optional)">
              <input className="cyber-input" type="email" value={createForm.email}
                onChange={e => setCreateForm(f => ({ ...f, email: e.target.value }))} />
            </Field>
            <Field label="Password">
              <input className="cyber-input" type="password" value={createForm.password}
                onChange={e => setCreateForm(f => ({ ...f, password: e.target.value }))} />
              <PasswordStrength password={createForm.password} />
            </Field>
            <Field label="Role">
              <select className="cyber-input" value={createForm.role}
                onChange={e => setCreateForm(f => ({ ...f, role: e.target.value as Role }))}>
                <option value="viewer">Viewer — read-only, all screens</option>
                <option value="planner">Planner — Indent / Purchase Requisition / Consumption (+ generate & create PR)</option>
                <option value="planner_view">Planner View — read-only on those 3 screens</option>
                <option value="master">Master — full access</option>
              </select>
            </Field>
            {isScopedRole(createForm.role) && (
              <LocationGrants
                hospitals={hospitals} stores={stores}
                hospitalIds={createForm.hospital_ids} storeIds={createForm.store_ids}
                onHospitalIds={ids => setCreateForm(f => ({ ...f, hospital_ids: ids }))}
                onStoreIds={ids => setCreateForm(f => ({ ...f, store_ids: ids }))}
              />
            )}
            {createMut.isError && (
              <p className="text-xs" style={{ color: 'var(--c-red)' }}>
                {(createMut.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to create user'}
              </p>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button className="btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
              <button
                className="btn-primary flex items-center gap-1"
                disabled={createMut.isPending || !createForm.username.trim() || !isPasswordValid(createForm.password)}
                onClick={() => createMut.mutate({
                  username: createForm.username,
                  email: createForm.email || undefined,
                  password: createForm.password,
                  role: createForm.role,
                  hospital_ids: isScopedRole(createForm.role) ? createForm.hospital_ids : [],
                  store_ids: isScopedRole(createForm.role) ? createForm.store_ids : [],
                })}
              >
                <Check size={13} /> Create
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Edit Modal ── */}
      {editId !== null && (
        <Modal title="Edit User" onClose={() => setEditId(null)}>
          <div className="space-y-3">
            <Field label="Email">
              <input className="cyber-input" type="email" value={editForm.email}
                onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))} />
            </Field>
            <Field label="Role">
              <select className="cyber-input" value={editForm.role}
                onChange={e => setEditForm(f => ({ ...f, role: e.target.value as Role }))}>
                <option value="viewer">Viewer — read-only, all screens</option>
                <option value="planner">Planner — Indent / Purchase Requisition / Consumption (+ generate & create PR)</option>
                <option value="planner_view">Planner View — read-only on those 3 screens</option>
                <option value="master">Master — full access</option>
              </select>
            </Field>
            {isScopedRole(editForm.role) && (
              <LocationGrants
                hospitals={hospitals} stores={stores}
                hospitalIds={editForm.hospital_ids} storeIds={editForm.store_ids}
                onHospitalIds={ids => setEditForm(f => ({ ...f, hospital_ids: ids }))}
                onStoreIds={ids => setEditForm(f => ({ ...f, store_ids: ids }))}
              />
            )}
            <Field label="Status">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={editForm.is_active}
                  onChange={e => setEditForm(f => ({ ...f, is_active: e.target.checked }))} />
                <span className="text-sm" style={{ color: 'var(--c-text)' }}>Active</span>
              </label>
            </Field>
            <div className="flex justify-end gap-2 pt-2">
              <button className="btn-secondary" onClick={() => setEditId(null)}>Cancel</button>
              <button
                className="btn-primary flex items-center gap-1"
                disabled={updateMut.isPending}
                onClick={() => updateMut.mutate({
                  id: editId,
                  data: {
                    email: editForm.email || undefined,
                    role: editForm.role,
                    is_active: editForm.is_active,
                    hospital_ids: isScopedRole(editForm.role) ? editForm.hospital_ids : [],
                    store_ids: isScopedRole(editForm.role) ? editForm.store_ids : [],
                  },
                })}
              >
                <Check size={13} /> Save
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Change Password Modal ── */}
      {pwdId !== null && (
        <Modal title="Change Password" onClose={() => setPwdId(null)}>
          <div className="space-y-3">
            <Field label="New Password">
              <input
                className="cyber-input"
                type="password"
                value={newPwd}
                onChange={e => setNewPwd(e.target.value)}
                placeholder="Enter new password"
              />
              <PasswordStrength password={newPwd} />
            </Field>
            {pwdMut.isError && (
              <p className="text-xs" style={{ color: 'var(--c-red)' }}>
                {(pwdMut.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to update password'}
              </p>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button className="btn-secondary" onClick={() => setPwdId(null)}>Cancel</button>
              <button
                className="btn-primary flex items-center gap-1"
                disabled={pwdMut.isPending || !isPasswordValid(newPwd)}
                onClick={() => pwdMut.mutate({ id: pwdId, password: newPwd })}
              >
                <KeyRound size={13} /> Update
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.6)' }}>
      <div
        className="w-full max-w-md rounded-xl p-6"
        style={{
          background: 'linear-gradient(135deg, var(--c-modal-from), var(--c-modal-to))',
          border: '1px solid var(--c-border)',
          boxShadow: '0 0 40px rgba(0,0,0,0.6)',
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-base" style={{ color: 'var(--c-text)' }}>{title}</h2>
          <button onClick={onClose} style={{ color: 'var(--c-text-sub)' }}
            onMouseEnter={e => (e.currentTarget.style.color = 'var(--c-text)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--c-text-sub)')}>
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs mb-1 font-medium" style={{ color: 'var(--c-text-sub)' }}>{label}</label>
      {children}
    </div>
  )
}

// Hospital + store grant editor, shown only for planner / planner_view users.
// Stores are grouped under collapsible hospital sections with a search box so
// the editor scales to many hospitals / hundreds of stores. A granted hospital
// implicitly covers all of its stores (now and future), shown as locked-checked.
function LocationGrants({
  hospitals, stores, hospitalIds, storeIds, onHospitalIds, onStoreIds,
}: {
  hospitals: { id: number; name: string; code: string }[]
  stores: { id: number; name: string; code: string; hospital_id: number }[]
  hospitalIds: number[]
  storeIds: number[]
  onHospitalIds: (ids: number[]) => void
  onStoreIds: (ids: number[]) => void
}) {
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const hSet = new Set(hospitalIds)
  const sSet = new Set(storeIds)
  const toggle = (ids: number[], id: number) =>
    ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id]

  const storesByHospital = useMemo(() => {
    const m = new Map<number, typeof stores>()
    for (const s of stores) {
      const arr = m.get(s.hospital_id) ?? []
      arr.push(s)
      m.set(s.hospital_id, arr)
    }
    return m
  }, [stores])

  const q = search.trim().toLowerCase()
  // When searching, only hospitals with a name/code match or a matching store
  // are shown, and matching stores are filtered within each section.
  const visible = useMemo(() => {
    return hospitals
      .map(h => {
        const own = storesByHospital.get(h.id) ?? []
        const hMatch = !q || h.name.toLowerCase().includes(q) || h.code.toLowerCase().includes(q)
        const matchedStores = q && !hMatch
          ? own.filter(s => s.code.toLowerCase().includes(q) || s.name.toLowerCase().includes(q))
          : own
        return { h, stores: matchedStores, visible: hMatch || matchedStores.length > 0 }
      })
      .filter(x => x.visible)
  }, [hospitals, storesByHospital, q])

  const grantedStoreCount = stores.filter(s => hSet.has(s.hospital_id) || sSet.has(s.id)).length
  const isSearching = q.length > 0
  const isOpen = (hid: number) => isSearching || expanded.has(hid)
  const toggleOpen = (hid: number) =>
    setExpanded(prev => { const n = new Set(prev); n.has(hid) ? n.delete(hid) : n.add(hid); return n })

  return (
    <Field label={`Store access — ${grantedStoreCount} store(s) granted`}>
      <p className="text-xs mb-2" style={{ color: 'var(--c-text-sub)' }}>
        Tick a hospital to grant all its stores (now and future), or expand it to pick individual stores.
        Only granted stores load in Indent, Consumption and Purchase Request. No selection = no access.
      </p>
      <div className="relative mb-2">
        <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--c-text-sub)' }} />
        <input className="cyber-input pl-7 text-sm" placeholder="Search hospital or store…"
          value={search} onChange={e => setSearch(e.target.value)} />
      </div>
      <div className="rounded border max-h-64 overflow-y-auto divide-y" style={{ borderColor: 'var(--c-border)' }}>
        {visible.length === 0 && (
          <div className="text-xs p-3" style={{ color: 'var(--c-text-sub)' }}>No matches.</div>
        )}
        {visible.map(({ h, stores: hStores }) => {
          const own = storesByHospital.get(h.id) ?? []
          const hGranted = hSet.has(h.id)
          const grantedHere = own.filter(s => hGranted || sSet.has(s.id)).length
          const open = isOpen(h.id)
          return (
            <div key={h.id} style={{ borderColor: 'var(--c-border)' }}>
              <div className="flex items-center gap-2 px-2 py-1.5">
                <button type="button" onClick={() => toggleOpen(h.id)}
                  className="p-0.5" style={{ color: 'var(--c-text-sub)' }} title={open ? 'Collapse' : 'Expand'}>
                  {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>
                <label className="flex items-center gap-2 text-sm cursor-pointer flex-1 min-w-0" style={{ color: 'var(--c-text)' }}>
                  <input type="checkbox" checked={hGranted}
                    onChange={() => onHospitalIds(toggle(hospitalIds, h.id))} />
                  <Building2 size={13} style={{ color: 'var(--c-text-sub)' }} />
                  <span className="truncate font-medium">{h.name}</span>
                </label>
                <span className="text-xs whitespace-nowrap" style={{ color: grantedHere ? 'var(--c-cyan)' : 'var(--c-text-sub)' }}>
                  {grantedHere}/{own.length}
                </span>
              </div>
              {open && (
                <div className="pl-8 pr-2 pb-1.5">
                  {hStores.length === 0 && <div className="text-xs py-0.5" style={{ color: 'var(--c-text-sub)' }}>No stores.</div>}
                  {hStores.map(s => {
                    const viaHospital = hGranted
                    return (
                      <label key={s.id} className="flex items-center gap-2 py-0.5 text-sm cursor-pointer"
                        style={{ color: viaHospital ? 'var(--c-text-sub)' : 'var(--c-text)' }}
                        title={viaHospital ? 'Included via its hospital grant' : ''}>
                        <input type="checkbox" checked={viaHospital || sSet.has(s.id)} disabled={viaHospital}
                          onChange={() => onStoreIds(toggle(storeIds, s.id))} />
                        <span className="truncate font-mono text-xs" style={{ color: 'var(--c-cyan)' }}>{s.code}</span>
                        <span className="truncate">{s.name}</span>
                      </label>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </Field>
  )
}
