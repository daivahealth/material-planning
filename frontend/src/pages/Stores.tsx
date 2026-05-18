import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getHospitals, getStores, createStore, updateStore, deleteStore } from '../api/client'
import PageHeader from '../components/PageHeader'
import Typeahead from '../components/Typeahead'
import TruncText from '../components/TruncText'
import { Plus, Pencil, Trash2 } from 'lucide-react'

type Store = { id: number; hospital_id: number; name: string; code: string }
type Form = { hospital_id: number; name: string; code: string }

export default function Stores() {
  const qc = useQueryClient()
  const [hospitalFilter, setHospitalFilter] = useState<number | ''>('')
  const [modal, setModal] = useState<'create' | Store | null>(null)
  const [form, setForm] = useState<Form>({ hospital_id: 0, name: '', code: '' })
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: hospitals = [] } = useQuery({ queryKey: ['hospitals'], queryFn: getHospitals })
  const { data: stores = [], isLoading } = useQuery({
    queryKey: ['stores', hospitalFilter],
    queryFn: () => getStores(hospitalFilter !== '' ? hospitalFilter : undefined),
  })

  const save = useMutation({
    mutationFn: () => modal === 'create' ? createStore(form) : updateStore((modal as Store).id, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['stores'] }); setModal(null) },
  })
  const remove = useMutation({
    mutationFn: (id: number) => deleteStore(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['stores'] }); setDeleteId(null) },
  })

  function openCreate() {
    setForm({ hospital_id: hospitalFilter !== '' ? hospitalFilter as number : (hospitals[0]?.id ?? 0), name: '', code: '' })
    setModal('create')
  }
  function openEdit(s: Store) { setForm({ hospital_id: s.hospital_id, name: s.name, code: s.code }); setModal(s) }
  const hospitalName = (id: number) => hospitals.find((h: any) => h.id === id)?.name ?? id

  const hospitalOptions = hospitals.map((h: any) => ({ value: String(h.id), label: h.name }))

  return (
    <div>
      <PageHeader title="Stores" actions={
        <button onClick={openCreate} className="btn-primary flex items-center gap-1"><Plus size={14} /> Add Store</button>
      }>
        <div className="flex gap-2 items-center mt-2">
          <label className="text-xs" style={{ color: 'var(--c-text-sub)' }}>Filter by hospital:</label>
          <Typeahead
            options={hospitalOptions}
            value={hospitalFilter !== '' ? String(hospitalFilter) : ''}
            onChange={v => setHospitalFilter(v === '' ? '' : Number(v))}
            placeholder="All"
            className="w-44"
          />
        </div>
      </PageHeader>

      {isLoading ? <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p> : (
        <div className="cyber-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="cyber-th">Hospital</th>
                <th className="cyber-th">Name</th>
                <th className="cyber-th">Code</th>
                <th className="cyber-th w-24">Actions</th>
              </tr>
            </thead>
            <tbody>
              {stores.map((s: Store) => (
                <tr key={s.id} className="cyber-tr">
                  <td className="px-4 py-2"><TruncText text={String(hospitalName(s.hospital_id))} style={{ color: 'var(--c-text)' }} /></td>
                  <td className="px-4 py-2 font-medium"><TruncText text={s.name} style={{ color: 'var(--c-text)' }} /></td>
                  <td className="px-4 py-2 font-mono text-xs" style={{ color: 'var(--c-cyan)' }}>{s.code}</td>
                  <td className="px-4 py-2">
                    <div className="flex gap-2">
                      <button onClick={() => openEdit(s)} style={{ color: 'var(--c-text-sub)' }} className="hover:text-[var(--c-cyan)] transition-colors"><Pencil size={14} /></button>
                      <button onClick={() => setDeleteId(s.id)} style={{ color: 'var(--c-text-sub)' }} className="hover:text-[var(--c-red)] transition-colors"><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {stores.length === 0 && <tr><td colSpan={4} className="px-4 py-6 text-center text-sm" style={{ color: 'var(--c-text-sub)' }}>No stores found.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {modal !== null && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h2 className="text-base font-semibold mb-4" style={{ color: 'var(--c-cyan)' }}>{modal === 'create' ? 'Add Store' : 'Edit Store'}</h2>
            <label className="form-label">Hospital</label>
            <Typeahead
              options={hospitalOptions}
              value={form.hospital_id ? String(form.hospital_id) : ''}
              onChange={v => setForm(f => ({ ...f, hospital_id: Number(v) }))}
              placeholder="Select hospital…"
            />
            <label className="form-label mt-3">Name</label>
            <input className="form-input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <label className="form-label mt-3">Code</label>
            <input className="form-input" value={form.code} onChange={e => setForm(f => ({ ...f, code: e.target.value }))} />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setModal(null)} className="btn-secondary">Cancel</button>
              <button onClick={() => save.mutate()} disabled={save.isPending} className="btn-primary">{save.isPending ? 'Saving…' : 'Save'}</button>
            </div>
            {save.isError && <p className="text-xs mt-2" style={{ color: 'var(--c-red)' }}>Error saving.</p>}
          </div>
        </div>
      )}

      {deleteId !== null && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <p className="text-sm mb-4" style={{ color: 'var(--c-text)' }}>Delete this store?</p>
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
