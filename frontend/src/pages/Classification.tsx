import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getHospitals, getStores, getItems, runFSN, getFSN, runVED, getVED, setVEDOverride } from '../api/client'
import PageHeader from '../components/PageHeader'
import Typeahead from '../components/Typeahead'
import TruncText from '../components/TruncText'
import { Play, Pencil } from 'lucide-react'

type Tab = 'fsn' | 'ved'

export default function Classification() {
  const [tab, setTab] = useState<Tab>('fsn')
  return (
    <div>
      <PageHeader title="FSN / VED Classification" />
      <div className="flex gap-4 mb-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
        {(['fsn', 'ved'] as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={tab === t ? 'cyber-tab-active' : 'cyber-tab'}>
            {t.toUpperCase()}
          </button>
        ))}
      </div>
      {tab === 'fsn' && <FSNTab />}
      {tab === 'ved' && <VEDTab />}
    </div>
  )
}

function FSNTab() {
  const qc = useQueryClient()
  const [hospitalId, setHospitalId] = useState('')
  const [classFilter, setClassFilter] = useState('')
  const [page, setPage] = useState(0)
  const LIMIT = 500

  const { data: hospitals = [] } = useQuery({ queryKey: ['hospitals'], queryFn: getHospitals })
  const { data: stores = [] } = useQuery({ queryKey: ['stores'], queryFn: () => getStores() })
  const { data: items = [] } = useQuery({ queryKey: ['items'], queryFn: () => getItems() })

  const { data: fsn = [], isLoading } = useQuery({
    queryKey: ['fsn', hospitalId, classFilter, page],
    queryFn: () => getFSN({
      hospital_id: hospitalId ? Number(hospitalId) : undefined,
      classification: classFilter || undefined,
      limit: LIMIT,
      offset: page * LIMIT,
    }),
    enabled: !!hospitalId,
  })

  const run = useMutation({
    mutationFn: () => runFSN(Number(hospitalId)),
    onSuccess: () => { setPage(0); qc.invalidateQueries({ queryKey: ['fsn'] }) },
  })

  // O(1) lookup maps instead of .find() per row
  const itemMap = useMemo(() => new Map(items.map((i: any) => [i.id, i.name])), [items])
  const storeMap = useMemo(() => new Map(stores.map((s: any) => [s.id, s.name])), [stores])

  return (
    <>
      <div className="flex gap-3 items-end mb-4 flex-wrap">
        <div>
          <label className="form-label">Hospital</label>
          <Typeahead
            options={hospitals.map((h: any) => ({ value: String(h.id), label: h.name }))}
            value={hospitalId}
            onChange={v => { setHospitalId(v); setPage(0) }}
            placeholder="Select hospital"
            className="w-52"
          />
        </div>
        <div>
          <label className="form-label">Class</label>
          <Typeahead
            options={[{ value: 'F', label: 'F — Fast' }, { value: 'S', label: 'S — Slow' }, { value: 'N', label: 'N — Non-moving' }]}
            value={classFilter}
            onChange={v => { setClassFilter(v); setPage(0) }}
            placeholder="All"
            className="w-36"
          />
        </div>
        <button onClick={() => run.mutate()} disabled={!hospitalId || run.isPending} className="btn-primary flex items-center gap-1">
          <Play size={14} /> {run.isPending ? 'Running…' : 'Run FSN'}
        </button>
        {run.isSuccess && <span className="text-xs" style={{ color: 'var(--c-green)' }}>FSN computed!</span>}
        {fsn.length > 0 && (
          <span className="text-xs ml-auto" style={{ color: 'var(--c-text-sub)' }}>
            Showing {page * LIMIT + 1}–{page * LIMIT + fsn.length}
            {fsn.length === LIMIT && '+'}
          </span>
        )}
      </div>

      {!hospitalId ? (
        <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Select a hospital to view FSN classifications.</p>
      ) : isLoading ? (
        <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p>
      ) : (
        <>
          <div className="cyber-panel overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className="cyber-th">Item</th>
                  <th className="cyber-th">Store</th>
                  <th className="cyber-th">Class</th>
                  <th className="cyber-th">Avg Daily</th>
                  <th className="cyber-th">Period Days</th>
                  <th className="cyber-th">Computed At</th>
                </tr>
              </thead>
              <tbody>
                {fsn.map((r: any) => {
                  const fsnBadge = r.classification === 'F' ? 'badge-green' : r.classification === 'S' ? 'badge-yellow' : 'badge-gray'
                  return (
                    <tr key={r.id} className="cyber-tr">
                      <td className="px-4 py-2"><TruncText text={itemMap.get(r.item_id) ?? String(r.item_id)} style={{ color: 'var(--c-text)' }} /></td>
                      <td className="px-4 py-2"><TruncText text={storeMap.get(r.store_id) ?? String(r.store_id)} style={{ color: 'var(--c-text)' }} /></td>
                      <td className="px-4 py-2"><span className={`${fsnBadge} font-bold`}>{r.classification}</span></td>
                      <td className="px-4 py-2" style={{ color: 'var(--c-text)' }}>{Number(r.avg_daily_consumption).toFixed(3)}</td>
                      <td className="px-4 py-2" style={{ color: 'var(--c-text)' }}>{r.period_days}</td>
                      <td className="px-4 py-2 text-xs" style={{ color: 'var(--c-text-sub)' }}>{r.computed_at ? new Date(r.computed_at).toLocaleString() : ''}</td>
                    </tr>
                  )
                })}
                {fsn.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-sm" style={{ color: 'var(--c-text-sub)' }}>No FSN data for this filter. Run FSN first.</td></tr>}
              </tbody>
            </table>
          </div>
          {/* Pagination */}
          {(page > 0 || fsn.length === LIMIT) && (
            <div className="flex gap-2 mt-3 justify-end">
              <button onClick={() => setPage(p => p - 1)} disabled={page === 0} className="btn-secondary">← Prev</button>
              <span className="text-xs self-center" style={{ color: 'var(--c-text-sub)' }}>Page {page + 1}</span>
              <button onClick={() => setPage(p => p + 1)} disabled={fsn.length < LIMIT} className="btn-secondary">Next →</button>
            </div>
          )}
        </>
      )}
    </>
  )
}

function VEDTab() {
  const qc = useQueryClient()
  const [overrideModal, setOverrideModal] = useState<{ item_id: number } | null>(null)
  const [overrideForm, setOverrideForm] = useState({ ved_class: 'V', reason: '' })
  const { data: items = [] } = useQuery({ queryKey: ['items'], queryFn: () => getItems() })
  const { data: ved = [], isLoading } = useQuery({ queryKey: ['ved'], queryFn: () => getVED() })
  const run = useMutation({
    mutationFn: runVED,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ved'] }),
  })
  const override = useMutation({
    mutationFn: () => setVEDOverride(overrideModal!.item_id, overrideForm),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ved'] }); setOverrideModal(null) },
  })

  const itemMap = useMemo(() => new Map(items.map((i: any) => [i.id, i.name])), [items])

  return (
    <>
      <div className="flex gap-3 mb-4">
        <button onClick={() => run.mutate()} disabled={run.isPending} className="btn-primary flex items-center gap-1">
          <Play size={14} /> {run.isPending ? 'Running…' : 'Run VED'}
        </button>
        {run.isSuccess && <span className="text-xs" style={{ color: 'var(--c-green)' }}>VED computed!</span>}
      </div>
      {isLoading ? <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p> : (
        <div className="cyber-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="cyber-th">Item</th>
                <th className="cyber-th">System</th>
                <th className="cyber-th">Override</th>
                <th className="cyber-th">Effective</th>
                <th className="cyber-th">Reason</th>
                <th className="cyber-th w-16">Edit</th>
              </tr>
            </thead>
            <tbody>
              {ved.map((r: any) => {
                const vedBadge = (c: string) => c === 'V' ? 'badge-red' : c === 'E' ? 'badge-yellow' : 'badge-gray'
                return (
                  <tr key={r.id} className="cyber-tr">
                    <td className="px-4 py-2"><TruncText text={itemMap.get(r.item_id) ?? String(r.item_id)} style={{ color: 'var(--c-text)' }} /></td>
                    <td className="px-4 py-2"><span className={`${vedBadge(r.system_suggestion)} font-bold`}>{r.system_suggestion}</span></td>
                    <td className="px-4 py-2">{r.manual_override ? <span className={`${vedBadge(r.manual_override)} font-bold`}>{r.manual_override}</span> : <span style={{ color: 'var(--c-text-sub)' }}>—</span>}</td>
                    <td className="px-4 py-2"><span className={`${vedBadge(r.effective_class)} font-bold`}>{r.effective_class}</span></td>
                    <td className="px-4 py-2 text-xs"><TruncText text={r.override_reason ?? ''} style={{ color: 'var(--c-text-sub)' }} /></td>
                    <td className="px-4 py-2">
                      <button onClick={() => { setOverrideModal({ item_id: r.item_id }); setOverrideForm({ ved_class: r.effective_class, reason: '' }) }} style={{ color: 'var(--c-text-sub)' }} className="hover:text-[var(--c-cyan)] transition-colors"><Pencil size={14} /></button>
                    </td>
                  </tr>
                )
              })}
              {ved.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-sm" style={{ color: 'var(--c-text-sub)' }}>No VED data. Run VED first.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {overrideModal && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h2 className="text-base font-semibold mb-4" style={{ color: 'var(--c-cyan)' }}>Override VED Class — Item {overrideModal.item_id}</h2>
            <label className="form-label">VED Class</label>
            <select className="form-input w-24" value={overrideForm.ved_class} onChange={e => setOverrideForm(f => ({ ...f, ved_class: e.target.value }))}>
              <option>V</option><option>E</option><option>D</option>
            </select>
            <label className="form-label mt-3">Reason</label>
            <input className="form-input" value={overrideForm.reason} onChange={e => setOverrideForm(f => ({ ...f, reason: e.target.value }))} />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setOverrideModal(null)} className="btn-secondary">Cancel</button>
              <button onClick={() => override.mutate()} disabled={override.isPending} className="btn-primary">{override.isPending ? 'Saving…' : 'Save'}</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
