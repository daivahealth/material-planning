import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSuppliers, createSupplier } from '../api/client'
import PageHeader from '../components/PageHeader'
import TruncText from '../components/TruncText'
import { Plus } from 'lucide-react'

export default function Suppliers() {
  const qc = useQueryClient()
  const [modal, setModal] = useState(false)
  const [form, setForm] = useState({ name: '', code: '', lead_time_days: 7 })

  const { data: suppliers = [], isLoading } = useQuery({ queryKey: ['suppliers'], queryFn: getSuppliers })

  const save = useMutation({
    mutationFn: () => createSupplier(form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); setModal(false) },
  })

  return (
    <div>
      <PageHeader title="Suppliers" actions={
        <button onClick={() => { setForm({ name: '', code: '', lead_time_days: 7 }); setModal(true) }} className="btn-primary flex items-center gap-1">
          <Plus size={14} /> Add Supplier
        </button>
      } />
      {isLoading ? <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p> : (
        <div className="cyber-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="cyber-th">Name</th>
                <th className="cyber-th">Code</th>
                <th className="cyber-th">Lead Time (days)</th>
              </tr>
            </thead>
            <tbody>
              {suppliers.map((s: any) => (
                <tr key={s.id} className="cyber-tr">
                  <td className="px-4 py-2 font-medium"><TruncText text={s.name} style={{ color: 'var(--c-text)' }} /></td>
                  <td className="px-4 py-2 font-mono text-xs" style={{ color: 'var(--c-cyan)' }}>{s.code}</td>
                  <td className="px-4 py-2" style={{ color: 'var(--c-text)' }}>{s.lead_time_days}</td>
                </tr>
              ))}
              {suppliers.length === 0 && <tr><td colSpan={3} className="px-4 py-6 text-center text-sm" style={{ color: 'var(--c-text-sub)' }}>No suppliers.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {modal && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h2 className="text-base font-semibold mb-4" style={{ color: 'var(--c-cyan)' }}>Add Supplier</h2>
            <label className="form-label">Name</label>
            <input className="form-input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <label className="form-label mt-3">Code</label>
            <input className="form-input" value={form.code} onChange={e => setForm(f => ({ ...f, code: e.target.value }))} />
            <label className="form-label mt-3">Lead Time (days)</label>
            <input type="number" className="form-input" value={form.lead_time_days} onChange={e => setForm(f => ({ ...f, lead_time_days: Number(e.target.value) }))} />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setModal(false)} className="btn-secondary">Cancel</button>
              <button onClick={() => save.mutate()} disabled={save.isPending} className="btn-primary">{save.isPending ? 'Saving…' : 'Save'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
