import { Fragment, useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getHospitals, getStores, getItems, getIndents, generateBatch, exportIndents, createSurge, clearIndents } from '../api/client'
import PageHeader from '../components/PageHeader'
import Typeahead from '../components/Typeahead'
import TruncText from '../components/TruncText'
import { Play, Download, Plus, Trash2, ChevronDown, ChevronRight } from 'lucide-react'

export default function IndentPlanning() {
  const qc = useQueryClient()
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())
  const [filters, setFilters] = useState({ store_id: '', item_id: '', hospital_id: '', period: '' })
  const [genStore, setGenStore] = useState('')
  const [surgeModal, setSurgeModal] = useState<{ item_id: number; store_id: number; item_label?: string; store_label?: string } | null>(null)
  const [surgeForm, setSurgeForm] = useState({ recorded_date: '', extra_qty: 0, reason: '', season: '' })
  const [showClearConfirm, setShowClearConfirm] = useState(false)

  const { data: hospitals = [] } = useQuery({ queryKey: ['hospitals'], queryFn: getHospitals })
  const { data: stores = [] } = useQuery({ queryKey: ['stores'], queryFn: () => getStores() })
  const { data: items = [] } = useQuery({ queryKey: ['items'], queryFn: () => getItems() })
  const { data: indents = [], isLoading } = useQuery({
    queryKey: ['indents', filters],
    queryFn: () => getIndents({
      store_id: filters.store_id ? Number(filters.store_id) : undefined,
      item_id: filters.item_id ? Number(filters.item_id) : undefined,
    }),
  })

  const generate = useMutation({
    mutationFn: () => generateBatch({ store_id: Number(genStore), triggered_by: 'manual' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['indents'] }),
  })

  const clearMutation = useMutation({
    mutationFn: () => clearIndents(filters.store_id ? { store_id: Number(filters.store_id) } : undefined),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['indents'] }); setShowClearConfirm(false) },
  })

  const addSurge = useMutation({
    mutationFn: () => createSurge({ ...surgeModal!, ...surgeForm, extra_qty: Number(surgeForm.extra_qty) }),
    onSuccess: () => setSurgeModal(null),
  })

  const exportUrl = exportIndents({
    store_id: filters.store_id || undefined,
    item_id: filters.item_id || undefined,
  })

  const hospitalOptions = useMemo(
    () => hospitals.map((h: any) => ({ value: String(h.id), label: h.name })),
    [hospitals]
  )
  const filteredStores = useMemo(
    () => filters.hospital_id
      ? stores.filter((s: any) => String(s.hospital_id) === filters.hospital_id)
      : stores,
    [stores, filters.hospital_id]
  )
  const storeOptions = useMemo(
    () => filteredStores.map((s: any) => ({ value: String(s.id), label: `${s.code} — ${s.name}` })),
    [filteredStores]
  )
  const allStoreOptions = useMemo(
    () => stores.map((s: any) => ({ value: String(s.id), label: `${s.code} — ${s.name}` })),
    [stores]
  )
  const itemOptions = useMemo(
    () => items.map((i: any) => ({ value: String(i.id), label: `${i.code} — ${i.name}` })),
    [items]
  )

  const periodOptions = useMemo(() => {
    const seen = new Set<string>()
    const opts: { value: string; label: string }[] = []
    for (const r of indents as any[]) {
      if (r.period_end && !seen.has(r.period_end)) {
        seen.add(r.period_end)
        opts.push({ value: r.period_end, label: `Up to ${r.period_end}` })
      }
    }
    return opts.sort((a, b) => a.value.localeCompare(b.value))
  }, [indents])

  const filteredIndents = useMemo(() =>
    filters.period
      ? (indents as any[]).filter((r: any) => r.period_end === filters.period)
      : (indents as any[]),
    [indents, filters.period]
  )

  return (
    <div>
      <PageHeader title="Indent Planning" actions={
        <div className="flex gap-2">
          <button onClick={() => setShowClearConfirm(true)} className="btn-danger flex items-center gap-1">
            <Trash2 size={14} /> Clear Indents
          </button>
          <a href={exportUrl} target="_blank" rel="noreferrer" className="btn-secondary flex items-center gap-1">
            <Download size={14} /> Export CSV
          </a>
        </div>
      } />

      {/* Generate batch */}
      <div className="cyber-panel p-4 mb-5 flex items-end gap-3 flex-wrap">
        <div>
          <label className="form-label">Store</label>
          <Typeahead
            options={allStoreOptions}
            value={genStore}
            onChange={setGenStore}
            placeholder="Select store…"
            className="w-56"
          />
        </div>
        <button
          onClick={() => generate.mutate()}
          disabled={!genStore || generate.isPending}
          className="btn-primary flex items-center gap-1"
        >
          <Play size={14} /> {generate.isPending ? 'Generating…' : 'Generate Batch'}
        </button>
        {generate.isSuccess && generate.data && (
          <span className="text-xs" style={{ color: 'var(--c-green)' }}>
            Generated {generate.data.generated} report(s) ({generate.data.skipped} skipped)
          </span>
        )}
        {generate.isError && <span className="text-xs" style={{ color: 'var(--c-red)' }}>Error generating.</span>}
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4 flex-wrap items-end">
        <div>
          <label className="form-label">Hospital</label>
          <Typeahead
            options={hospitalOptions}
            value={filters.hospital_id}
            onChange={v => setFilters(f => ({ ...f, hospital_id: v, store_id: '' }))}
            placeholder="All hospitals"
            className="w-44"
          />
        </div>
        <div>
          <label className="form-label">Store</label>
          <Typeahead
            options={storeOptions}
            value={filters.store_id}
            onChange={v => setFilters(f => ({ ...f, store_id: v }))}
            placeholder="All stores"
            className="w-52"
          />
        </div>
        <div>
          <label className="form-label">Item</label>
          <Typeahead
            options={itemOptions}
            value={filters.item_id}
            onChange={v => setFilters(f => ({ ...f, item_id: v }))}
            placeholder="All items"
            className="w-56"
          />
        </div>
        <div>
          <label className="form-label">Period</label>
          <Typeahead
            options={periodOptions}
            value={filters.period}
            onChange={v => setFilters(f => ({ ...f, period: v }))}
            placeholder="All periods"
            className="w-44"
          />
        </div>
      </div>

      {/* Table */}
      {isLoading ? <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p> : (
        <div className="cyber-panel overflow-hidden overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className="cyber-th">Item</th>
                <th className="cyber-th">Store</th>
                <th className="cyber-th">Period</th>
                <th className="cyber-th">Avg Daily</th>
                <th className="cyber-th">Closing Stk</th>
                <th className="cyber-th">Open Indent</th>
                <th className="cyber-th">Base Qty</th>
                <th className="cyber-th">Surge Qty</th>
                <th className="cyber-th">Total Qty</th>
                <th className="cyber-th">Surge</th>
              </tr>
            </thead>
            <tbody>
              {filteredIndents.map((r: any) => {
                const itemCode = r.item_code ?? String(r.item_id)
                const itemName = r.item_name ?? itemCode
                const storeCode = r.store_code ?? String(r.store_id)
                const storeName = r.store_name ?? storeCode
                const itemFull = r.item_name ? `${r.item_code} — ${r.item_name}` : itemCode
                const storeFull = r.store_name ? `${r.store_code} (${r.store_name})` : storeCode
                const isExpanded = expandedRows.has(r.id)
                const toggleExpand = () => setExpandedRows(prev => {
                  const next = new Set(prev)
                  isExpanded ? next.delete(r.id) : next.add(r.id)
                  return next
                })
                return (
                  <Fragment key={r.id}>
                    <tr key={r.id} className="cyber-tr">
                      <td className="px-3 py-1.5">
                        <button
                          onClick={toggleExpand}
                          className="flex items-center gap-1"
                          style={{ color: 'var(--c-cyan)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                        >
                          {isExpanded
                            ? <ChevronDown size={11} style={{ opacity: 0.7, flexShrink: 0 }} />
                            : <ChevronRight size={11} style={{ opacity: 0.5, flexShrink: 0 }} />
                          }
                          <TruncText text={itemName} maxLen={24} startLen={13} endLen={8} style={{ color: 'var(--c-text)', fontSize: '0.75rem' }} />
                        </button>
                      </td>
                      <td className="px-3 py-1.5">
                        <TruncText text={storeName} maxLen={22} startLen={12} endLen={7} style={{ color: 'var(--c-text-sub)', fontSize: '0.75rem' }} />
                      </td>
                      <td className="px-3 py-1.5" style={{ color: 'var(--c-text-sub)' }}>{r.period_start} → {r.period_end}</td>
                      <td className="px-3 py-1.5" style={{ color: 'var(--c-text)' }}>{Number(r.avg_daily_consumption ?? 0).toFixed(2)}</td>
                      <td className="px-3 py-1.5" style={{ color: 'var(--c-text)' }}>{Number(r.closing_stock_qty ?? 0).toFixed(0)}</td>
                      <td className="px-3 py-1.5 font-medium" style={{ color: 'var(--c-purple)' }}>{Number(r.open_indent_qty ?? 0).toFixed(0)}</td>
                      <td className="px-3 py-1.5 font-medium" style={{ color: 'var(--c-text)' }}>{Number(r.base_indent_qty ?? 0).toFixed(0)}</td>
                      <td className="px-3 py-1.5 font-medium" style={{ color: 'var(--c-orange)' }}>{Number(r.surge_indent_qty ?? 0).toFixed(0)}</td>
                      <td className="px-3 py-1.5 font-bold" style={{ color: 'var(--c-cyan)' }}>{Number(r.total_indent_qty ?? 0).toFixed(0)}</td>
                      <td className="px-3 py-1.5">
                        <button
                          onClick={() => {
                            setSurgeModal({ item_id: r.item_id, store_id: r.store_id, item_label: itemFull, store_label: storeFull })
                            setSurgeForm({ recorded_date: '', extra_qty: 0, reason: '', season: '' })
                          }}
                          style={{ color: 'var(--c-text-sub)' }}
                          className="hover:text-[var(--c-orange)] transition-colors"
                        >
                          <Plus size={13} />
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${r.id}-detail`} style={{ background: 'rgba(0,212,255,0.025)' }}>
                        <td colSpan={10} style={{ padding: '0.35rem 2.5rem 0.55rem', borderBottom: '1px solid rgba(0,212,255,0.07)' }}>
                          <div className="flex gap-6 text-xs flex-wrap">
                            <span>
                              <span style={{ color: 'var(--c-text-sub)', marginRight: '0.35rem' }}>Item code:</span>
                              <span className="font-mono" style={{ color: 'var(--c-cyan)' }}>{itemCode}</span>
                            </span>
                            <span>
                              <span style={{ color: 'var(--c-text-sub)', marginRight: '0.35rem' }}>Store code:</span>
                              <span className="font-mono" style={{ color: 'var(--c-cyan)' }}>{storeCode}</span>
                            </span>
                            {r.triggered_by && (
                              <span>
                                <span style={{ color: 'var(--c-text-sub)', marginRight: '0.35rem' }}>Triggered by:</span>
                                <span style={{ color: 'var(--c-text)' }}>{r.triggered_by}</span>
                              </span>
                            )}
                            {r.item_name && (
                              <span>
                                <span style={{ color: 'var(--c-text-sub)', marginRight: '0.35rem' }}>Item:</span>
                                <span style={{ color: 'var(--c-text)' }}>{r.item_name}</span>
                              </span>
                            )}
                            {r.store_name && (
                              <span>
                                <span style={{ color: 'var(--c-text-sub)', marginRight: '0.35rem' }}>Store:</span>
                                <span style={{ color: 'var(--c-text)' }}>{r.store_name}</span>
                              </span>
                            )}
                            {r.hospital_name && (
                              <span>
                                <span style={{ color: 'var(--c-text-sub)', marginRight: '0.35rem' }}>Hospital:</span>
                                <span style={{ color: 'var(--c-text)' }}>{r.hospital_name}</span>
                              </span>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
              {filteredIndents.length === 0 && (
                <tr><td colSpan={10} className="px-4 py-6 text-center" style={{ color: 'var(--c-text-sub)' }}>
                  {(indents as any[]).length > 0 ? 'No records match the selected period.' : 'No indent reports. Generate a batch first.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Clear confirmation dialog */}
      {showClearConfirm && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h2 className="text-base font-semibold mb-3" style={{ color: 'var(--c-red)' }}>Clear Indent Reports</h2>
            <p className="text-sm mb-4" style={{ color: 'var(--c-text)' }}>
              {filters.store_id
                ? `Delete all indent reports for the selected store?`
                : 'Delete ALL indent reports across all stores?'}
              {' '}This cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowClearConfirm(false)} className="btn-secondary">Cancel</button>
              <button
                onClick={() => clearMutation.mutate()}
                disabled={clearMutation.isPending}
                className="btn-danger"
              >
                {clearMutation.isPending ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Surge modal */}
      {surgeModal && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h2 className="text-base font-semibold mb-4" style={{ color: 'var(--c-cyan)' }}>Add Surge Record</h2>
            <p className="text-xs mb-3" style={{ color: 'var(--c-text-sub)' }}>
              {surgeModal.item_label} / {surgeModal.store_label}
            </p>
            <label className="form-label">Recorded Date</label>
            <input type="date" className="form-input" value={surgeForm.recorded_date}
              onChange={e => setSurgeForm(f => ({ ...f, recorded_date: e.target.value }))} />
            <label className="form-label mt-3">Extra Qty</label>
            <input type="number" className="form-input" value={surgeForm.extra_qty}
              onChange={e => setSurgeForm(f => ({ ...f, extra_qty: Number(e.target.value) }))} />
            <label className="form-label mt-3">Reason</label>
            <input className="form-input" value={surgeForm.reason}
              onChange={e => setSurgeForm(f => ({ ...f, reason: e.target.value }))} />
            <label className="form-label mt-3">Season (optional)</label>
            <Typeahead
              options={[
                { value: 'Summer', label: 'Summer' },
                { value: 'Monsoon', label: 'Monsoon' },
                { value: 'Winter', label: 'Winter' },
                { value: 'Festive', label: 'Festive' },
              ]}
              value={surgeForm.season}
              onChange={v => setSurgeForm(f => ({ ...f, season: v }))}
              placeholder="Auto-detect"
            />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setSurgeModal(null)} className="btn-secondary">Cancel</button>
              <button onClick={() => addSurge.mutate()} disabled={addSurge.isPending} className="btn-primary">
                {addSurge.isPending ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

