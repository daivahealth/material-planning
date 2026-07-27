import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSuppliers, createSupplier, updateSupplier } from '../api/client'
import PageHeader from '../components/PageHeader'
import TruncText from '../components/TruncText'
import { Plus, Pencil, Search } from 'lucide-react'

type Supplier = { id: number; name: string; code: string; lead_time_days: number }
type Form = { name: string; code: string; lead_time_days: number }

export default function Suppliers() {
  const qc = useQueryClient()
  const [modal, setModal] = useState<'create' | Supplier | null>(null)
  const [form, setForm] = useState<Form>({ name: '', code: '', lead_time_days: 7 })
  const [search, setSearch] = useState('')

  const { data: suppliers = [], isLoading } = useQuery({ queryKey: ['suppliers'], queryFn: getSuppliers })

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return suppliers as Supplier[]
    return (suppliers as Supplier[]).filter(s =>
      s.name.toLowerCase().includes(q) || s.code.toLowerCase().includes(q))
  }, [suppliers, search])

  const save = useMutation({
    mutationFn: () => modal === 'create'
      ? createSupplier(form)
      : updateSupplier((modal as Supplier).id, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); setModal(null) },
  })

  function openCreate() { setForm({ name: '', code: '', lead_time_days: 7 }); setModal('create') }
  function openEdit(s: Supplier) { setForm({ name: s.name, code: s.code, lead_time_days: s.lead_time_days }); setModal(s) }

  return (
    <div>
      <PageHeader title="Suppliers" actions={
        <button onClick={openCreate} className="btn-primary flex items-center gap-1">
          <Plus size={14} /> Add Supplier
        </button>
      }>
        <div className="flex gap-2 items-center mt-2">
          <div className="relative w-64">
            <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--c-text-sub)' }} />
            <input
              className="form-input pl-7"
              placeholder="Filter by name or code…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>
      </PageHeader>
      {isLoading ? <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p> : (
        <div className="cyber-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="cyber-th">Name</th>
                <th className="cyber-th">Code</th>
                <th className="cyber-th">Lead Time (days)</th>
                <th className="cyber-th w-16">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s: Supplier) => (
                <tr key={s.id} className="cyber-tr">
                  <td className="px-4 py-2 font-medium"><TruncText text={s.name} style={{ color: 'var(--c-text)' }} /></td>
                  <td className="px-4 py-2 font-mono text-xs" style={{ color: 'var(--c-cyan)' }}>{s.code}</td>
                  <td className="px-4 py-2" style={{ color: 'var(--c-text)' }}>{s.lead_time_days}</td>
                  <td className="px-4 py-2">
                    <button onClick={() => openEdit(s)} style={{ color: 'var(--c-text-sub)' }} className="hover:text-[var(--c-cyan)] transition-colors"><Pencil size={14} /></button>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && <tr><td colSpan={4} className="px-4 py-6 text-center text-sm" style={{ color: 'var(--c-text-sub)' }}>{(suppliers as Supplier[]).length === 0 ? 'No suppliers.' : 'No suppliers match the filter.'}</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {modal !== null && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h2 className="text-base font-semibold mb-4" style={{ color: 'var(--c-cyan)' }}>{modal === 'create' ? 'Add Supplier' : 'Edit Supplier'}</h2>
            <label className="form-label">Name</label>
            <input className="form-input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <label className="form-label mt-3">Code</label>
            <input className="form-input" value={form.code} onChange={e => setForm(f => ({ ...f, code: e.target.value }))} />
            <label className="form-label mt-3">Lead Time (days)</label>
            <input type="number" min={0} className="form-input" value={form.lead_time_days} onChange={e => setForm(f => ({ ...f, lead_time_days: Number(e.target.value) }))} />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setModal(null)} className="btn-secondary">Cancel</button>
              <button onClick={() => save.mutate()} disabled={save.isPending} className="btn-primary">{save.isPending ? 'Saving…' : 'Save'}</button>
            </div>
            {save.isError && <p className="text-xs mt-2" style={{ color: 'var(--c-red)' }}>Error saving.</p>}
          </div>
        </div>
      )}
    </div>
  )
}
