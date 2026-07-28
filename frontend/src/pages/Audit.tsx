import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getAuditLogs } from '../api/client'
import PageHeader from '../components/PageHeader'
import TruncText from '../components/TruncText'
import { Search, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'

type AuditRow = {
  id: number
  actor_id: number | null
  actor_username: string | null
  actor_role: string | null
  action: string
  entity: string
  entity_id: string | null
  summary: string | null
  details: Record<string, any> | null
  ip_address: string | null
  created_at: string
}

type Filters = {
  actor: string; action: string; entity: string
  from_date: string; to_date: string; limit: number
}

const EMPTY: Filters = { actor: '', action: '', entity: '', from_date: '', to_date: '', limit: 50 }

// Colour by what the action does, so destructive entries stand out.
function actionColor(action: string): string {
  if (action.startsWith('delete') || action === 'clear') return 'var(--c-red)'
  if (action === 'create') return 'var(--c-green)'
  if (action === 'login_failed') return 'var(--c-orange)'
  if (action === 'login') return 'var(--c-text-sub)'
  return 'var(--c-cyan)'
}

function DetailRow({ row }: { row: AuditRow }) {
  const entries = Object.entries(row.details ?? {})
  if (entries.length === 0) {
    return <span className="text-xs" style={{ color: 'var(--c-text-sub)' }}>No further detail recorded.</span>
  }
  // Field changes are stored as {from, to}; anything else is shown as a value.
  return (
    <table className="text-xs w-full">
      <thead>
        <tr style={{ color: 'var(--c-text-sub)' }}>
          <th className="text-left pb-1 pr-4">Field</th>
          <th className="text-left pb-1 pr-4">From</th>
          <th className="text-left pb-1">To</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([field, val]) => {
          const isChange = val && typeof val === 'object' && ('from' in val || 'to' in val)
          const fmt = (v: any) => v === null || v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v)
          return (
            <tr key={field} style={{ borderTop: '1px solid var(--c-border)' }}>
              <td className="py-0.5 pr-4 font-mono" style={{ color: 'var(--c-text)' }}>{field}</td>
              <td className="py-0.5 pr-4 font-mono" style={{ color: 'var(--c-text-sub)' }}>
                {isChange ? fmt(val.from) : ''}
              </td>
              <td className="py-0.5 font-mono" style={{ color: 'var(--c-cyan)' }}>
                {isChange ? fmt(val.to) : fmt(val)}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export default function Audit() {
  // `applied` is what the query actually uses — typing in a box doesn't refetch
  // until Search is pressed, so a large trail isn't queried on every keystroke.
  const [form, setForm] = useState<Filters>(EMPTY)
  const [applied, setApplied] = useState<Filters>(EMPTY)
  const [open, setOpen] = useState<Set<number>>(new Set())

  const { data: rows = [], isLoading, isFetching, isError, error, refetch } = useQuery<AuditRow[]>({
    queryKey: ['audit', applied],
    queryFn: () => getAuditLogs({
      actor: applied.actor || undefined,
      action: applied.action || undefined,
      entity: applied.entity || undefined,
      from_date: applied.from_date || undefined,
      to_date: applied.to_date || undefined,
      limit: applied.limit,
    }),
  })

  const toggle = (id: number) =>
    setOpen(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })

  const set = (k: keyof Filters, v: string | number) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div>
      <PageHeader title="Audit Trail" actions={
        <button onClick={() => refetch()} disabled={isFetching}
          className="btn-secondary flex items-center gap-1">
          <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} /> Refresh
        </button>
      }>
        Who changed what, and when. Newest first — showing the latest {applied.limit} records.
      </PageHeader>

      <div className="cyber-panel p-4 mb-4">
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          <div>
            <label className="form-label">Actor</label>
            <input className="form-input" placeholder="username" value={form.actor}
              onChange={e => set('actor', e.target.value)} />
          </div>
          <div>
            <label className="form-label">Action</label>
            <input className="form-input" placeholder="create / update / login…" value={form.action}
              onChange={e => set('action', e.target.value)} />
          </div>
          <div>
            <label className="form-label">Entity</label>
            <input className="form-input" placeholder="user / store_settings…" value={form.entity}
              onChange={e => set('entity', e.target.value)} />
          </div>
          <div>
            <label className="form-label">From</label>
            <input type="date" className="form-input" value={form.from_date}
              onChange={e => set('from_date', e.target.value)} />
          </div>
          <div>
            <label className="form-label">To</label>
            <input type="date" className="form-input" value={form.to_date}
              onChange={e => set('to_date', e.target.value)} />
          </div>
          <div>
            <label className="form-label">Show</label>
            <select className="form-input" value={form.limit}
              onChange={e => set('limit', Number(e.target.value))}>
              <option value={50}>Latest 50</option>
              <option value={100}>Latest 100</option>
              <option value={250}>Latest 250</option>
              <option value={1000}>Latest 1000</option>
            </select>
          </div>
        </div>
        <div className="flex gap-2 mt-3">
          <button className="btn-primary flex items-center gap-1" onClick={() => setApplied(form)}>
            <Search size={13} /> Search
          </button>
          <button className="btn-secondary" onClick={() => { setForm(EMPTY); setApplied(EMPTY) }}>
            Reset
          </button>
        </div>
      </div>

      {isError && (
        <p className="text-sm mb-3" style={{ color: 'var(--c-red)' }}>
          {(error as any)?.response?.data?.detail ?? 'Failed to load audit records'}
        </p>
      )}

      {isLoading ? (
        <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p>
      ) : (
        <div className="cyber-panel overflow-hidden overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className="cyber-th" style={{ width: 30 }}></th>
                <th className="cyber-th">When</th>
                <th className="cyber-th">Actor</th>
                <th className="cyber-th">Action</th>
                <th className="cyber-th">Entity</th>
                <th className="cyber-th">Summary</th>
                <th className="cyber-th">IP</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const expandable = !!r.details && Object.keys(r.details).length > 0
                const isOpen = open.has(r.id)
                return [
                  <tr key={r.id} className="cyber-tr">
                    <td className="px-2 py-1.5">
                      {expandable && (
                        <button onClick={() => toggle(r.id)} style={{ color: 'var(--c-text-sub)' }}
                          title={isOpen ? 'Hide changes' : 'Show changes'}>
                          {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                        </button>
                      )}
                    </td>
                    <td className="px-3 py-1.5 font-mono whitespace-nowrap" style={{ color: 'var(--c-text-sub)' }}>
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-1.5" style={{ color: 'var(--c-text)' }}>
                      {r.actor_username ?? <span style={{ color: 'var(--c-text-sub)' }}>—</span>}
                      {r.actor_role && (
                        <span className="ml-1 text-xs" style={{ color: 'var(--c-text-sub)' }}>({r.actor_role})</span>
                      )}
                    </td>
                    <td className="px-3 py-1.5 font-medium whitespace-nowrap" style={{ color: actionColor(r.action) }}>
                      {r.action}
                    </td>
                    <td className="px-3 py-1.5 font-mono" style={{ color: 'var(--c-text-sub)' }}>
                      {r.entity}{r.entity_id ? ` #${r.entity_id}` : ''}
                    </td>
                    <td className="px-3 py-1.5" style={{ color: 'var(--c-text)' }}>
                      <TruncText text={r.summary ?? ''} maxLen={70} startLen={50} endLen={16} />
                    </td>
                    <td className="px-3 py-1.5 font-mono" style={{ color: 'var(--c-text-sub)' }}>
                      {r.ip_address ?? '—'}
                    </td>
                  </tr>,
                  isOpen && (
                    <tr key={`${r.id}-d`}>
                      <td colSpan={7} className="px-8 py-2" style={{ background: 'rgba(0,0,0,0.2)' }}>
                        <DetailRow row={r} />
                      </td>
                    </tr>
                  ),
                ]
              })}
              {rows.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-6 text-center" style={{ color: 'var(--c-text-sub)' }}>
                  No audit records match these filters.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {rows.length > 0 && (
        <p className="text-xs mt-2" style={{ color: 'var(--c-text-sub)' }}>
          {rows.length} record(s){rows.length === applied.limit && ' — limit reached; narrow the filters or increase "Show" to see older entries.'}
        </p>
      )}
    </div>
  )
}
