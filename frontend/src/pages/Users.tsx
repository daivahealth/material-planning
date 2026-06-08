import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getUsers, createUser, updateUser, deleteUser, changePassword } from '../api/client'
import PageHeader from '../components/PageHeader'
import { PasswordStrength, isPasswordValid } from '../components/PasswordStrength'
import { useAuth } from '../contexts/AuthContext'
import { Plus, Pencil, Trash2, KeyRound, ShieldCheck, Eye, X, Check } from 'lucide-react'

type Role = 'master' | 'viewer'

interface UserRow {
  id: number
  username: string
  email: string | null
  role: Role
  is_active: boolean
  created_at: string
  updated_at: string
}

interface UserFormState {
  username: string
  email: string
  password: string
  role: Role
}

interface EditFormState {
  email: string
  role: Role
  is_active: boolean
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

  const [showCreate, setShowCreate] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [pwdId, setPwdId] = useState<number | null>(null)
  const [newPwd, setNewPwd] = useState('')
  const [createForm, setCreateForm] = useState<UserFormState>({
    username: '', email: '', password: '', role: 'viewer',
  })
  const [editForm, setEditForm] = useState<EditFormState>({ email: '', role: 'viewer', is_active: true })

  const refetch = () => qc.invalidateQueries({ queryKey: ['users'] })

  const createMut = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      setShowCreate(false)
      setCreateForm({ username: '', email: '', password: '', role: 'viewer' })
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

  const pwdMut = useMutation({
    mutationFn: ({ id, password }: { id: number; password: string }) => changePassword(id, password),
    onSuccess: () => { setPwdId(null); setNewPwd('') },
  })

  const startEdit = (u: UserRow) => {
    setEditId(u.id)
    setEditForm({ email: u.email ?? '', role: u.role, is_active: u.is_active })
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
      {role === 'master' ? 'Master' : 'Viewer'}
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
                <option value="viewer">Viewer — read-only access</option>
                <option value="master">Master — full access</option>
              </select>
            </Field>
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
                <option value="viewer">Viewer — read-only access</option>
                <option value="master">Master — full access</option>
              </select>
            </Field>
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
