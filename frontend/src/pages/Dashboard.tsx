import { useQuery } from '@tanstack/react-query'
import { getHospitals, getStores, getItems, getIndents, getSurges, getSchedulerStatus } from '../api/client'
import StatCard from '../components/StatCard'
import PageHeader from '../components/PageHeader'
import TruncText from '../components/TruncText'

export default function Dashboard() {
  const { data: hospitals = [] } = useQuery({ queryKey: ['hospitals'], queryFn: getHospitals })
  const { data: stores = [] } = useQuery({ queryKey: ['stores'], queryFn: () => getStores() })
  const { data: items = [] } = useQuery({ queryKey: ['items'], queryFn: () => getItems() })
  // Fetch only 5 most recent records for dashboard display
  const { data: indents = [] } = useQuery({ queryKey: ['indents', { limit: 5 }], queryFn: () => getIndents({ limit: 5 }) })
  const { data: surges = [] } = useQuery({ queryKey: ['surges', { limit: 5 }], queryFn: () => getSurges(undefined, undefined, 5) })
  const { data: scheduler } = useQuery({ queryKey: ['scheduler'], queryFn: getSchedulerStatus, staleTime: 60_000 })

  const recentIndents = indents.slice(0, 5)
  const recentSurges = surges.slice(0, 5)

  return (
    <div>
      <PageHeader title="Dashboard" />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard label="Hospitals" value={hospitals.length} color="blue" />
        <StatCard label="Stores" value={stores.length} color="purple" />
        <StatCard label="Items" value={items.length} color="green" />
        <StatCard label="Indent Reports" value={indents.length} color="yellow" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Recent Indent Reports */}
        <div className="cyber-panel p-4">
          <h2 className="cyber-section-title">Recent Indent Reports</h2>
          {recentIndents.length === 0 ? (
            <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>No indent reports yet.</p>
          ) : (
            <table className="w-full text-xs">
              <thead><tr>
                <th className="cyber-th">Item</th>
                <th className="cyber-th">Store</th>
                <th className="cyber-th">Total Qty</th>
                <th className="cyber-th">Period End</th>
              </tr></thead>
              <tbody>
                {recentIndents.map((r: any) => (
                  <tr key={r.id} className="cyber-tr">
                    <td className="px-4 py-2 font-mono">{(() => { const lbl = r.item_code ? `${r.item_code}${r.item_name ? ' — ' + r.item_name : ''}` : String(r.item_id); return <TruncText text={lbl} style={{ color: 'var(--c-text)' }} mono /> })()}</td>
                    <td className="px-4 py-2"><TruncText text={r.store_name ?? String(r.store_id)} style={{ color: 'var(--c-text)' }} /></td>
                    <td className="px-4 py-2 font-medium" style={{ color: 'var(--c-cyan)' }}>{Number(r.total_indent_qty).toFixed(0)}</td>
                    <td className="px-4 py-2" style={{ color: 'var(--c-text-sub)' }}>{r.period_end}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Recent Surges */}
        <div className="cyber-panel p-4">
          <h2 className="cyber-section-title">Recent Surge Records</h2>
          {recentSurges.length === 0 ? (
            <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>No surge records yet.</p>
          ) : (
            <table className="w-full text-xs">
              <thead><tr>
                <th className="cyber-th">Item</th>
                <th className="cyber-th">Season</th>
                <th className="cyber-th">Extra Qty</th>
                <th className="cyber-th">Reason</th>
              </tr></thead>
              <tbody>
                {recentSurges.map((s: any) => {
                  const item = items.find((i: any) => i.id === s.item_id)
                  return (
                    <tr key={s.id} className="cyber-tr">
                      <td className="px-4 py-2 font-mono">{(() => { const lbl = item ? `${item.code}${item.name ? ' — ' + item.name : ''}` : String(s.item_id); return <TruncText text={lbl} style={{ color: 'var(--c-text)' }} mono /> })()}</td>
                      <td className="px-4 py-2"><span className="badge-orange">{s.season}</span></td>
                      <td className="px-4 py-2 font-medium" style={{ color: 'var(--c-orange)' }}>{s.extra_qty}</td>
                      <td className="px-4 py-2"><TruncText text={s.reason} style={{ color: 'var(--c-text-sub)' }} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Scheduler status */}
      <div className="cyber-panel p-4">
        <h2 className="cyber-section-title">Scheduler Status</h2>
        {!scheduler?.jobs?.length ? (
          <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>No scheduled jobs running.</p>
        ) : (
          <table className="w-full text-xs">
            <thead><tr>
              <th className="cyber-th">Job ID</th>
              <th className="cyber-th">Next Run</th>
              <th className="cyber-th">Trigger</th>
            </tr></thead>
            <tbody>
              {scheduler.jobs.map((j: any) => (
                <tr key={j.job_id} className="cyber-tr">
                  <td className="px-4 py-2 font-mono" style={{ color: 'var(--c-cyan)' }}>{j.job_id}</td>
                  <td className="px-4 py-2" style={{ color: 'var(--c-text)' }}>{j.next_run_time ? new Date(j.next_run_time).toLocaleString() : 'N/A'}</td>
                  <td className="px-4 py-2" style={{ color: 'var(--c-text-sub)' }}>{j.trigger}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
