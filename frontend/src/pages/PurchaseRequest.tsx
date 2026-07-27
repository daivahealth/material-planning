import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getStores, getPRCandidates, createPurchaseRequest } from '../api/client'
import PageHeader from '../components/PageHeader'
import Typeahead from '../components/Typeahead'
import TruncText from '../components/TruncText'
import { FileText, Search } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { canCreatePR } from '../utils/permissions'

export default function PurchaseRequest() {
  const qc = useQueryClient()
  const { user } = useAuth()
  const mayCreate = canCreatePR(user?.role)
  const [storeId, setStoreId] = useState('')
  const [period, setPeriod] = useState('')
  const [supplier, setSupplier] = useState('')
  const [itemSearch, setItemSearch] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [result, setResult] = useState<string>('')

  const { data: stores = [] } = useQuery({ queryKey: ['stores'], queryFn: () => getStores() })

  const { data: candidates = [], isError, error } = useQuery({
    queryKey: ['prCandidates', storeId],
    queryFn: () => getPRCandidates(Number(storeId)),
    enabled: storeId !== '',
    retry: false,
  })
  const storeErr = isError ? ((error as any)?.response?.data?.detail || 'Unable to load candidates') : ''

  // Derived dropdown options from the candidate set
  const periodOptions = useMemo(() => {
    const seen = new Set<string>()
    return (candidates as any[])
      .filter(c => c.period_start && !seen.has(c.period_start) && (seen.add(c.period_start), true))
      .map(c => ({ value: c.period_start, label: `${c.period_start} → ${c.period_end}` }))
      .sort((a, b) => b.value.localeCompare(a.value))
  }, [candidates])

  const supplierOptions = useMemo(() => {
    const map = new Map<string, string>()
    for (const c of candidates as any[]) if (c.preferred_supplier_code) map.set(c.preferred_supplier_code, c.preferred_supplier_name || '')
    return [...map.entries()].map(([code, name]) => ({ value: code, label: `${code}${name ? ' — ' + name : ''}` }))
  }, [candidates])

  const rows = useMemo(() => {
    const q = itemSearch.trim().toLowerCase()
    return (candidates as any[]).filter(c =>
      (!period || c.period_start === period) &&
      (!supplier || c.preferred_supplier_code === supplier) &&
      (!q || (c.item_code || '').toLowerCase().includes(q) || (c.item_name || '').toLowerCase().includes(q))
    )
  }, [candidates, period, supplier, itemSearch])

  const allSelected = rows.length > 0 && rows.every(r => selected.has(r.item_id))
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(rows.map(r => r.item_id)))
  const toggleOne = (id: number) => setSelected(prev => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n
  })

  // The period for the request is derived from the selected lines — the user
  // doesn't have to touch the Period dropdown (which is only a filter). If the
  // selection spans multiple periods, they must narrow it via the dropdown.
  const selectedRows = useMemo(() => rows.filter(r => selected.has(r.item_id)), [rows, selected])
  const selectedPeriods = useMemo(() => [...new Set(selectedRows.map(r => r.period_start))], [selectedRows])
  const effectivePeriod = period || (selectedPeriods.length === 1 ? selectedPeriods[0] : '')
  const multiPeriod = selectedRows.length > 0 && !effectivePeriod

  const create = useMutation({
    mutationFn: () => createPurchaseRequest({
      store_id: Number(storeId), period_start: effectivePeriod,
      item_ids: selectedRows.map(r => r.item_id),
    }),
    onSuccess: (r: any) => {
      setResult(`Created ${r.request_number} · ${r.rows} line(s)`)
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ['prCandidates', storeId] })
    },
  })

  const canCreate = mayCreate && selectedRows.length > 0 && !!effectivePeriod && !create.isPending

  return (
    <div>
      <PageHeader title="Create Purchase Request" actions={
        <button onClick={() => create.mutate()} disabled={!canCreate}
          className="btn-primary flex items-center gap-1">
          <FileText size={14} /> {create.isPending ? 'Creating…' : `Create Purchase Request${selected.size ? ` (${selected.size})` : ''}`}
        </button>
      } />

      <p className="text-xs mb-4" style={{ color: 'var(--c-text-sub)' }}>
        Select a purchase-request store and period, pick items (optionally filter by preferred supplier), and raise a
        Purchase Request. Selected lines are written to the outbound table as <strong>PurchaseRequest</strong>, the
        request number is published to Kafka, and those lines are flagged so they can't be requested again.
      </p>

      <div className="flex flex-wrap gap-3 mb-4 items-end">
        <div>
          <label className="form-label">Store</label>
          <Typeahead
            options={stores.map((s: any) => ({ value: String(s.id), label: `${s.code} — ${s.name}` }))}
            value={storeId}
            onChange={v => { setStoreId(v); setPeriod(''); setSupplier(''); setItemSearch(''); setSelected(new Set()); setResult('') }}
            placeholder="Select store…" className="w-60"
          />
        </div>
        <div>
          <label className="form-label">Period</label>
          <Typeahead options={periodOptions} value={period}
            onChange={v => { setPeriod(v); setSelected(new Set()) }}
            placeholder="Select period…" className="w-52" />
        </div>
        <div>
          <label className="form-label">Preferred Supplier</label>
          <Typeahead options={supplierOptions} value={supplier}
            onChange={v => { setSupplier(v); setSelected(new Set()) }}
            placeholder="All suppliers" className="w-56" />
        </div>
        <div>
          <label className="form-label">Item</label>
          <div className="relative w-56">
            <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--c-text-sub)' }} />
            <input className="form-input pl-7" placeholder="Filter by code or name…"
              value={itemSearch}
              onChange={e => { setItemSearch(e.target.value); setSelected(new Set()) }} />
          </div>
        </div>
      </div>

      {result && <div className="mb-3 text-sm" style={{ color: 'var(--c-green)' }}>{result}</div>}
      {storeErr && <div className="mb-3 text-sm" style={{ color: 'var(--c-red)' }}>{storeErr}</div>}
      {multiPeriod && <div className="mb-3 text-sm" style={{ color: 'var(--c-orange)' }}>
        Selected items span multiple periods — pick a Period to create the request.
      </div>}

      {storeId && !storeErr && (
        <div className="cyber-panel overflow-hidden overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className="cyber-th" style={{ width: 36 }}>
                  <input type="checkbox" checked={allSelected} onChange={toggleAll} disabled={rows.length === 0} />
                </th>
                <th className="cyber-th">Item</th>
                <th className="cyber-th">Pref. Supplier</th>
                <th className="cyber-th">Period</th>
                <th className="cyber-th">Qty</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: any) => (
                <tr key={r.id} className="cyber-tr">
                  <td className="px-3 py-1.5">
                    <input type="checkbox" checked={selected.has(r.item_id)} onChange={() => toggleOne(r.item_id)} />
                  </td>
                  <td className="px-3 py-1.5">
                    <span className="font-mono" style={{ color: 'var(--c-cyan)' }}>{r.item_code}</span>
                    <span style={{ color: 'var(--c-text-sub)' }}> · </span>
                    <TruncText text={r.item_name || ''} maxLen={26} startLen={14} endLen={8} style={{ color: 'var(--c-text)' }} />
                  </td>
                  <td className="px-3 py-1.5">
                    {r.preferred_supplier_code
                      ? <><span className="font-mono" style={{ color: 'var(--c-cyan)' }}>{r.preferred_supplier_code}</span><span style={{ color: 'var(--c-text-sub)' }}> {r.preferred_supplier_name}</span></>
                      : <span style={{ color: 'var(--c-text-sub)' }}>—</span>}
                  </td>
                  <td className="px-3 py-1.5" style={{ color: 'var(--c-text-sub)' }}>{r.period_start} → {r.period_end}</td>
                  <td className="px-3 py-1.5 font-bold" style={{ color: 'var(--c-cyan)' }}>{Number(r.total_indent_qty).toFixed(0)}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-6 text-center" style={{ color: 'var(--c-text-sub)' }}>
                  {(candidates as any[]).length === 0 ? 'No indent lines pending a purchase request for this store.' : 'No lines match the selected period / supplier.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
