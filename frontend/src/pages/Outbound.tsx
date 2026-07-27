import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getOutboundSettings, upsertOutboundSettings, testOutboundConnection,
  runOutboundNow, getOutboundDispatches,
} from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import PageHeader from '../components/PageHeader'

const MAPPING_FIELDS = ['item_code', 'store_code', 'qty', 'request_number', 'request_type', 'inserted_date', 'request_status']

export default function Outbound() {
  const qc = useQueryClient()
  const { isMaster } = useAuth()
  const [form, setForm] = useState<any>({})
  const [pwd, setPwd] = useState('')
  const [testMsg, setTestMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [runMsg, setRunMsg] = useState('')

  const { data: settings } = useQuery({ queryKey: ['outboundSettings'], queryFn: getOutboundSettings })
  const { data: dispatches = [] } = useQuery({ queryKey: ['outboundDispatches'], queryFn: () => getOutboundDispatches() })

  useEffect(() => {
    if (settings) setForm(settings)
    else if (settings === null) setForm({ db_type: 'postgresql', request_status_value: 'NEW', request_type_value: 'StockIndent', kafka_topic: 'material_planning_event', enabled: false, column_mapping: {} })
  }, [settings])

  const update = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }))
  const updateMap = (field: string, col: string) =>
    setForm((f: any) => ({ ...f, column_mapping: { ...(f.column_mapping || {}), [field]: col } }))

  const save = useMutation({
    mutationFn: () => {
      const payload: any = { ...form }
      delete payload.id; delete payload.has_password
      delete payload.last_run_at; delete payload.last_run_status; delete payload.last_error
      if (pwd) payload.password = pwd
      return upsertOutboundSettings(payload)
    },
    onSuccess: () => { setPwd(''); qc.invalidateQueries({ queryKey: ['outboundSettings'] }) },
  })

  const test = useMutation({
    mutationFn: testOutboundConnection,
    onSuccess: (r: any) => setTestMsg({ ok: !!r.success, text: r.success ? 'Connection OK' : (r.error || 'Failed') }),
    onError: () => setTestMsg({ ok: false, text: 'Save connection details first' }),
  })

  const run = useMutation({
    mutationFn: runOutboundNow,
    onSuccess: (r: any) => {
      setRunMsg(r.skipped ? `Skipped: ${r.reason}` : `Dispatched ${r.stores_dispatched} store(s)`)
      qc.invalidateQueries({ queryKey: ['outboundDispatches'] })
    },
  })

  const inp = (label: string, key: string, type = 'text', placeholder = '') => (
    <div>
      <label className="form-label">{label}</label>
      <input type={type} className="form-input" placeholder={placeholder}
        value={form[key] ?? ''} disabled={!isMaster}
        onChange={e => update(key, type === 'number' ? (e.target.value === '' ? null : Number(e.target.value)) : e.target.value)} />
    </div>
  )

  return (
    <div>
      <PageHeader title="Outbound Settings" actions={
        isMaster ? (
          <div className="flex gap-2">
            <button onClick={() => test.mutate()} disabled={test.isPending} className="btn-secondary">
              {test.isPending ? 'Testing…' : 'Test Connection'}
            </button>
            <button onClick={() => run.mutate()} disabled={run.isPending} className="btn-primary">
              {run.isPending ? 'Running…' : 'Run Now'}
            </button>
          </div>
        ) : undefined
      } />

      <p className="text-xs mb-4" style={{ color: 'var(--c-text-sub)' }}>
        Scheduled pipeline: generate indents for <strong>stock-indent</strong> stores, write lines to the external
        outbound table, allocate a per-store request number, and publish it to Kafka.
      </p>

      {(testMsg || runMsg) && (
        <div className="mb-3 text-sm">
          {testMsg && <span style={{ color: testMsg.ok ? 'var(--c-green)' : 'var(--c-red)' }}>{testMsg.text}</span>}
          {runMsg && <span style={{ color: 'var(--c-cyan)', marginLeft: 12 }}>{runMsg}</span>}
        </div>
      )}

      <div className="cyber-panel p-4 max-w-3xl">
        <label className="inline-flex items-center gap-2 mb-3 text-sm" style={{ color: 'var(--c-text)' }}>
          <input type="checkbox" checked={form.enabled ?? false} disabled={!isMaster}
            onChange={e => update('enabled', e.target.checked)} />
          Pipeline Enabled
        </label>

        <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--c-cyan)' }}>Target Database</h3>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="form-label">DB Type</label>
            <select className="form-input" value={form.db_type ?? 'postgresql'} disabled={!isMaster}
              onChange={e => update('db_type', e.target.value)}>
              <option value="postgresql">PostgreSQL</option>
              <option value="mysql">MySQL</option>
              <option value="oracle">Oracle</option>
            </select>
          </div>
          {inp('Host', 'host')}
          {inp('Port', 'port', 'number')}
          {inp('Database', 'database_name')}
          {inp('Username', 'username')}
          <div>
            <label className="form-label">Password</label>
            <input type="password" className="form-input" disabled={!isMaster}
              placeholder={form.has_password ? '•••••• (unchanged)' : ''}
              value={pwd} onChange={e => setPwd(e.target.value)} />
          </div>
          {inp('Target Table', 'target_table', 'text', 'e.g. outbound_indents')}
          {inp('Request Type Value', 'request_type_value', 'text', 'StockIndent')}
          {inp('Request Status Value', 'request_status_value', 'text', 'NEW')}
        </div>

        <h3 className="text-sm font-semibold mt-4 mb-2" style={{ color: 'var(--c-cyan)' }}>Column Mapping</h3>
        <p className="text-xs mb-2" style={{ color: 'var(--c-text-sub)' }}>Internal field → target column (leave blank to use the same name).</p>
        <div className="grid grid-cols-3 gap-3">
          {MAPPING_FIELDS.map(field => (
            <div key={field}>
              <label className="form-label">{field}</label>
              <input className="form-input" placeholder={field} disabled={!isMaster}
                value={(form.column_mapping || {})[field] ?? ''}
                onChange={e => updateMap(field, e.target.value)} />
            </div>
          ))}
        </div>

        <h3 className="text-sm font-semibold mt-4 mb-2" style={{ color: 'var(--c-cyan)' }}>Schedule &amp; Kafka</h3>
        <div className="grid grid-cols-3 gap-3">
          {inp('Schedule (cron, 5-field)', 'schedule_cron', 'text', '0 18 * * *')}
          {inp('Kafka Topic', 'kafka_topic', 'text', 'material_planning_event')}
          {inp('Kafka Brokers (override)', 'kafka_brokers', 'text', 'from KAFKA_BROKERS env')}
        </div>

        {isMaster && (
          <div className="flex items-center gap-3 justify-end mt-4">
            {form.last_run_status && (
              <span className="text-xs" style={{ color: 'var(--c-text-sub)' }}>
                Last run: {form.last_run_status}{form.last_run_at ? ` · ${new Date(form.last_run_at).toLocaleString()}` : ''}
              </span>
            )}
            <button onClick={() => save.mutate()} disabled={save.isPending} className="btn-primary">
              {save.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        )}
      </div>

      <h3 className="text-sm font-semibold mt-6 mb-2" style={{ color: 'var(--c-text)' }}>Recent Dispatches</h3>
      <div className="cyber-panel overflow-hidden overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="cyber-th">Request #</th>
              <th className="cyber-th">Store</th>
              <th className="cyber-th">Period Start</th>
              <th className="cyber-th">Rows</th>
              <th className="cyber-th">Status</th>
              <th className="cyber-th">Published</th>
            </tr>
          </thead>
          <tbody>
            {dispatches.map((d: any) => (
              <tr key={d.id} className="cyber-tr">
                <td className="px-3 py-1.5 font-mono" style={{ color: 'var(--c-cyan)' }}>{d.request_number}</td>
                <td className="px-3 py-1.5" style={{ color: 'var(--c-text-sub)' }}>{d.store_id}</td>
                <td className="px-3 py-1.5" style={{ color: 'var(--c-text-sub)' }}>{d.period_start}</td>
                <td className="px-3 py-1.5" style={{ color: 'var(--c-text)' }}>{d.rows_written}</td>
                <td className="px-3 py-1.5">
                  <span style={{ color: d.status === 'published' ? 'var(--c-green)' : d.status === 'failed' ? 'var(--c-red)' : 'var(--c-orange)' }}>
                    {d.status}
                  </span>
                </td>
                <td className="px-3 py-1.5" style={{ color: 'var(--c-text-sub)' }}>
                  {d.published_at ? new Date(d.published_at).toLocaleString() : '—'}
                </td>
              </tr>
            ))}
            {dispatches.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-6 text-center" style={{ color: 'var(--c-text-sub)' }}>No dispatches yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
