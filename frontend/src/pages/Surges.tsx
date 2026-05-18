import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getSurges, getItems, getStores } from '../api/client'
import PageHeader from '../components/PageHeader'
import Typeahead from '../components/Typeahead'
import TruncText from '../components/TruncText'

export default function Surges() {
  const [itemId, setItemId] = useState('')
  const [storeId, setStoreId] = useState('')

  const { data: items = [] } = useQuery({ queryKey: ['items'], queryFn: () => getItems() })
  const { data: stores = [] } = useQuery({ queryKey: ['stores'], queryFn: () => getStores() })
  const { data: surges = [], isLoading } = useQuery({
    queryKey: ['surges', itemId, storeId],
    queryFn: () => getSurges(itemId ? Number(itemId) : undefined, storeId ? Number(storeId) : undefined),
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
              </tr>
            </thead>
            <tbody>
              {surges.map((s: any) => (
                <tr key={s.id} className="cyber-tr">
                  <td className="px-4 py-2"><TruncText text={itemName(s.item_id)} style={{ color: 'var(--c-text)' }} /></td>
                  <td className="px-4 py-2"><TruncText text={storeName(s.store_id)} style={{ color: 'var(--c-text)' }} /></td>
                  <td className="px-4 py-2" style={{ color: 'var(--c-text-sub)' }}>{s.recorded_date}</td>
                  <td className="px-4 py-2">
                    <span className="badge-orange">{s.season}</span>
                  </td>
                  <td className="px-4 py-2 font-medium" style={{ color: 'var(--c-orange)' }}>{s.extra_qty}</td>
                  <td className="px-4 py-2"><TruncText text={s.reason} style={{ color: 'var(--c-text-sub)' }} /></td>
                </tr>
              ))}
              {surges.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-sm" style={{ color: 'var(--c-text-sub)' }}>No surge records.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
