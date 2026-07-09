import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSurges, getItems, getStores, updateSurge } from '../api/client'
import PageHeader from '../components/PageHeader'
import Typeahead from '../components/Typeahead'
import TruncText from '../components/TruncText'

function fmtDate(iso: string): string {
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export default function Surges() {
  const qc = useQueryClient()
  const [itemId, setItemId] = useState('')
  const [storeId, setStoreId] = useState('')

  const { data: items = [] } = useQuery({ queryKey: ['items'], queryFn: () => getItems() })
  const { data: stores = [] } = useQuery({ queryKey: ['stores'], queryFn: () => getStores() })
  const { data: surges = [], isLoading } = useQuery({
    queryKey: ['surges', itemId, storeId],
    queryFn: () => getSurges(itemId ? Number(itemId) : undefined, storeId ? Number(storeId) : undefined),
  })

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => updateSurge(id, { enabled }),
    onSuccess: () => {
      // Toggling changes what the indent calculation sees — refresh both.
      qc.invalidateQueries({ queryKey: ['surges'] })
      qc.invalidateQueries({ queryKey: ['indents'] })
    },
  })

  const itemName = (id: number) => { const i = items.find((x: any) => x.id === id); return i ? `${i.code} — ${i.name}` : String(id) }
  const storeName = (id: number) => { const s = stores.find((x: any) => x.id === id); return s ? `${s.code} (${s.name})` : String(id) }
  const itemOptions = items.map((i: any) => ({ value: String(i.id), label: `${i.code} — ${i.name}` }))
  const storeOptions = stores.map((s: any) => ({ value: String(s.id), label: `${s.code} — ${s.name}` }))

  return (
    <div>
      <PageHeader title="Surge Records" />
      <div className="flex gap-3 mb-4 items-end">
        <div>
          <label className="form-label">Item</label>
          <Typeahead options={itemOptions} value={itemId} onChange={setItemId} placeholder="All items" className="w-56" />
        </div>
        <div>
          <label className="form-label">Store</label>
          <Typeahead options={storeOptions} value={storeId} onChange={setStoreId} placeholder="All stores" className="w-52" />
        </div>
      </div>
      <p className="text-xs mb-3" style={{ color: 'var(--c-text-sub)' }}>
        Disabled surge records are excluded from indent calculation. Toggling recomputes the affected item's indent.
      </p>
      {isLoading ? <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p> : (
        <div className="cyber-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="cyber-th">Item</th>
                <th className="cyber-th">Store</th>
                <th className="cyber-th">Date</th>
                <th className="cyber-th">Season</th>
                <th className="cyber-th">Extra Qty</th>
                <th className="cyber-th">Reason</th>
                <th className="cyber-th">Status</th>
              </tr>
            </thead>
            <tbody>
              {surges.map((s: any) => {
                const enabled = s.enabled !== false
                return (
                  <tr key={s.id} className="cyber-tr" style={{ opacity: enabled ? 1 : 0.5 }}>
                    <td className="px-4 py-2"><TruncText text={itemName(s.item_id)} style={{ color: 'var(--c-text)' }} /></td>
                    <td className="px-4 py-2"><TruncText text={storeName(s.store_id)} style={{ color: 'var(--c-text)' }} /></td>
                    <td className="px-4 py-2" style={{ color: 'var(--c-text-sub)' }}>{s.recorded_date}</td>
                    <td className="px-4 py-2">
                      <span className="badge-orange">{s.season}</span>
                    </td>
                    <td className="px-4 py-2 font-medium" style={{ color: 'var(--c-orange)' }}>{s.extra_qty}</td>
                    <td className="px-4 py-2"><TruncText text={s.reason} style={{ color: 'var(--c-text-sub)' }} /></td>
                    <td className="px-4 py-2">
                      <button
                        onClick={() => toggle.mutate({ id: s.id, enabled: !enabled })}
                        disabled={toggle.isPending}
                        className={enabled ? 'btn-secondary' : 'btn-primary'}
                        style={{ minWidth: '5.5rem' }}
                      >
                        {enabled ? 'Disable' : 'Enable'}
                      </button>
                      {!enabled && s.disabled_by && (
                        <div className="text-xs mt-1" style={{ color: 'var(--c-text-sub)' }}>
                          by <span style={{ color: 'var(--c-text)' }}>{s.disabled_by}</span>
                          {s.disabled_at && <> · {fmtDate(s.disabled_at)}</>}
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
              {surges.length === 0 && <tr><td colSpan={7} className="px-4 py-6 text-center text-sm" style={{ color: 'var(--c-text-sub)' }}>No surge records.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
