import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getHospitals, createHospital, updateHospital, deleteHospital } from '../api/client'
import PageHeader from '../components/PageHeader'
import TruncText from '../components/TruncText'
import { Plus, Pencil, Trash2 } from 'lucide-react'

type Hospital = { id: number; name: string; code: string }
type Form = { name: string; code: string }

const empty: Form = { name: '', code: '' }

export default function Hospitals() {
  const qc = useQueryClient()
  const [modal, setModal] = useState<'create' | Hospital | null>(null)
  const [form, setForm] = useState<Form>(empty)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: hospitals = [], isLoading } = useQuery({ queryKey: ['hospitals'], queryFn: getHospitals })

  const save = useMutation({
    mutationFn: () => modal === 'create' ? createHospital(form) : updateHospital((modal as Hospital).id, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['hospitals'] }); setModal(null) },
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteHospital(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['hospitals'] }); setDeleteId(null) },
  })

  function openCreate() { setForm(empty); setModal('create') }
  function openEdit(h: Hospital) { setForm({ name: h.name, code: h.code }); setModal(h) }

  return (
    <div>
      <PageHeader title="Hospitals" actions={
        <button onClick={openCreate} className="btn-primary flex items-center gap-1">
          <Plus size={14} /> Add Hospital
        </button>
      } />

      {isLoading ? <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p> : (
        <div className="cyber-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="cyber-th">Name</th>
                <th className="cyber-th">Code</th>
                <th className="cyber-th w-24">Actions</th>
              </tr>
            </thead>
            <tbody>
              {hospitals.map((h: Hospital) => (
                <tr key={h.id} className="cyber-tr">
                  <td className="px-4 py-2 font-medium"><TruncText text={h.name} style={{ color: 'var(--c-text)' }} /></td>
                  <td className="px-4 py-2 font-mono text-xs" style={{ color: 'var(--c-cyan)' }}>{h.code}</td>
                  <td className="px-4 py-2">
                    <div className="flex gap-2">
                      <button onClick={() => openEdit(h)} style={{ color: 'var(--c-text-sub)' }} className="hover:text-[var(--c-cyan)] transition-colors"><Pencil size={14} /></button>
                      <button onClick={() => setDeleteId(h.id)} style={{ color: 'var(--c-text-sub)' }} className="hover:text-[var(--c-red)] transition-colors"><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {hospitals.length === 0 && <tr><td colSpan={3} className="px-4 py-6 text-center text-sm" style={{ color: 'var(--c-text-sub)' }}>No hospitals found.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {/* Create / Edit modal */}
      {modal !== null && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h2 className="text-base font-semibold mb-4" style={{ color: 'var(--c-cyan)' }}>{modal === 'create' ? 'Add Hospital' : 'Edit Hospital'}</h2>
            <label className="form-label">Name</label>
            <input className="form-input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <label className="form-label mt-3">Code</label>
            <input className="form-input" value={form.code} onChange={e => setForm(f => ({ ...f, code: e.target.value }))} />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setModal(null)} className="btn-secondary">Cancel</button>
              <button onClick={() => save.mutate()} disabled={save.isPending} className="btn-primary">
                {save.isPending ? 'Saving…' : 'Save'}
              </button>
            </div>
            {save.isError && <p className="text-xs mt-2" style={{ color: 'var(--c-red)' }}>Error saving.</p>}
          </div>
        </div>
      )}

      {/* Delete confirm */}
      {deleteId !== null && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <p className="text-sm mb-4" style={{ color: 'var(--c-text)' }}>Delete this hospital? This cannot be undone.</p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteId(null)} className="btn-secondary">Cancel</button>
              <button onClick={() => remove.mutate(deleteId)} className="btn-danger">Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
