import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getDataMiningStatus, createDataMiningConfig, updateDataMiningConfig,
  deleteDataMiningConfig, testDataMiningConnection, runDataMining,
  getDataMiningRuns,
} from '../api/client'
import PageHeader from '../components/PageHeader'
import { Database, Play, Plus, Pencil, Trash2, ChevronDown, ChevronRight, CheckCircle2, XCircle, Loader2, Clock } from 'lucide-react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type DataType = 'consumption' | 'closing_stock' | 'open_indent' | 'item' | 'supplier'
type DbType = 'postgresql' | 'mysql' | 'oracle'
type RunStatus = 'never' | 'running' | 'success' | 'error'

interface MiningConfig {
  id: number
  name: string
  description: string | null
  data_type: DataType
  db_type: DbType
  host: string
  port: number
  database_name: string
  username: string
  query: string
  page_size: number
  column_mapping: Record<string, string>
  enabled: boolean
  schedule_cron: string | null
  last_run_at: string | null
  last_run_status: RunStatus
  last_rows_fetched: number | null
  last_rows_inserted: number | null
  last_rows_skipped: number | null
  last_error: string | null
  created_at: string
  updated_at: string
}

interface MiningRun {
  id: number
  config_id: number
  started_at: string
  ended_at: string | null
  status: RunStatus
  rows_fetched: number
  rows_inserted: number
  rows_skipped: number
  error_message: string | null
}

interface StatusEntry {
  config: MiningConfig
  latest_run: MiningRun | null
}

// ---------------------------------------------------------------------------
// Column-mapping field definitions per data type
// ---------------------------------------------------------------------------
const REQUIRED_FIELDS: Record<DataType, string[]> = {
  consumption: ['item_code', 'store_code', 'date', 'quantity'],
  closing_stock: ['item_code', 'store_code', 'date', 'quantity'],
  open_indent: ['item_code', 'store_code', 'as_of_date', 'quantity'],
  item: ['code', 'name'],
  supplier: ['code', 'name'],
}
const OPTIONAL_FIELDS: Record<DataType, string[]> = {
  consumption: [],
  closing_stock: [],
  open_indent: [],
  item: ['unit', 'group_name', 'category_name'],
  supplier: ['lead_time_days'],
}
const DATA_TYPE_LABELS: Record<DataType, string> = {
  consumption: 'Consumption',
  closing_stock: 'Closing Stock',
  open_indent: 'Open Indent',
  item: 'Item',
  supplier: 'Supplier',
}
const DEFAULT_PORTS: Record<DbType, number> = { postgresql: 5432, mysql: 3306, oracle: 1521 }

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const emptyForm = (): any => ({
  name: '', description: '', data_type: 'consumption' as DataType,
  db_type: 'postgresql' as DbType, host: '', port: 5432, database_name: '',
  username: '', password: '', query: '', page_size: 1000,
  column_mapping: {}, enabled: true, schedule_cron: '',
})

function StatusBadge({ status }: { status: RunStatus }) {
  if (status === 'success') return <span className="badge-green flex items-center gap-1"><CheckCircle2 size={11} />Success</span>
  if (status === 'error') return <span className="badge-red flex items-center gap-1"><XCircle size={11} />Error</span>
  if (status === 'running') return <span className="badge-cyan flex items-center gap-1"><Loader2 size={11} className="animate-spin" />Running</span>
  return <span className="badge-gray flex items-center gap-1"><Clock size={11} />Never</span>
}

function fmtDuration(start: string, end: string | null) {
  if (!end) return '—'
  const ms = new Date(end).getTime() - new Date(start).getTime()
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

// ---------------------------------------------------------------------------
// Config modal
// ---------------------------------------------------------------------------
const TABS = ['Info', 'Connection', 'Query & Pagination', 'Column Mapping']

interface ConfigModalProps {
  initial: any
  onClose: () => void
  onSave: (data: any) => void
  isSaving: boolean
}

function ConfigModal({ initial, onClose, onSave, isSaving }: ConfigModalProps) {
  const [tab, setTab] = useState(0)
  const [form, setForm] = useState<any>({ ...emptyForm(), ...initial })
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [testing, setTesting] = useState(false)

  const isEdit = !!initial?.id

  const set = (field: string, val: any) => setForm((f: any) => ({ ...f, [field]: val }))
  const setMapping = (key: string, val: string) =>
    setForm((f: any) => ({ ...f, column_mapping: { ...f.column_mapping, [key]: val } }))

  const handleDbTypeChange = (dt: DbType) => {
    setForm((f: any) => ({ ...f, db_type: dt, port: DEFAULT_PORTS[dt] }))
  }

  const handleTest = async () => {
    if (!initial?.id) { setTestResult({ success: false, message: 'Save the config first before testing.' }); return }
    setTesting(true)
    try {
      const r = await testDataMiningConnection(initial.id)
      setTestResult(r)
    } catch {
      setTestResult({ success: false, message: 'Request failed.' })
    } finally {
      setTesting(false)
    }
  }

  const handleSubmit = () => {
    const payload: any = {
      name: form.name,
      description: form.description || null,
      data_type: form.data_type,
      db_type: form.db_type,
      host: form.host,
      port: Number(form.port),
      database_name: form.database_name,
      username: form.username,
      query: form.query,
      page_size: Number(form.page_size),
      column_mapping: form.column_mapping,
      enabled: form.enabled,
      schedule_cron: form.schedule_cron || null,
    }
    if (!isEdit || form.password) payload.password = form.password
    onSave(payload)
  }

  const requiredFields = REQUIRED_FIELDS[form.data_type as DataType] ?? []
  const optionalFields = OPTIONAL_FIELDS[form.data_type as DataType] ?? []

  const labelStyle = { color: 'var(--c-text-sub)', fontSize: '0.75rem', fontWeight: 500, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }
  const inputStyle = { background: 'var(--c-input-bg)', border: '1px solid var(--c-bdr)', borderRadius: 4, padding: '0.35rem 0.6rem', fontSize: '0.85rem', color: 'var(--c-text)', width: '100%' }
  const fieldRow = (label: string, children: React.ReactNode) => (
    <div className="mb-3">
      <label style={labelStyle}>{label}</label>
      <div className="mt-1">{children}</div>
    </div>
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.65)' }}>
      <div className="cyber-panel w-full max-w-2xl max-h-[90vh] flex flex-col" style={{ minWidth: 540 }}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: '1px solid var(--c-bdr)' }}>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--c-cyan)' }}>
            {isEdit ? 'Edit Data Mining Config' : 'Add Data Mining Config'}
          </h2>
          <button onClick={onClose} style={{ color: 'var(--c-text-sub)', fontSize: '1.1rem' }}>✕</button>
        </div>

        {/* Tabs */}
        <div className="flex border-b" style={{ borderColor: 'var(--c-bdr)' }}>
          {TABS.map((t, i) => (
            <button
              key={t}
              onClick={() => setTab(i)}
              className="px-4 py-2 text-xs font-medium"
              style={{
                color: tab === i ? 'var(--c-cyan)' : 'var(--c-text-sub)',
                borderBottom: tab === i ? '2px solid var(--c-cyan)' : '2px solid transparent',
                background: 'none',
              }}
            >{t}</button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {/* --- Tab 0: Info --- */}
          {tab === 0 && (
            <div>
              {fieldRow('Name *', <input style={inputStyle} value={form.name} onChange={e => set('name', e.target.value)} placeholder="e.g. HIS Consumption Sync" />)}
              {fieldRow('Description', <textarea style={{ ...inputStyle, height: 60, resize: 'vertical' }} value={form.description || ''} onChange={e => set('description', e.target.value)} placeholder="Optional description" />)}
              {fieldRow('Data Type *',
                <select style={inputStyle} value={form.data_type} onChange={e => set('data_type', e.target.value)}>
                  {(Object.entries(DATA_TYPE_LABELS) as [DataType, string][]).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              )}
              <div className="mb-3 flex items-center gap-3">
                <label style={labelStyle}>Enabled</label>
                <input type="checkbox" checked={form.enabled} onChange={e => set('enabled', e.target.checked)} />
              </div>
              {fieldRow('Schedule (cron)', <input style={inputStyle} value={form.schedule_cron || ''} onChange={e => set('schedule_cron', e.target.value)} placeholder='e.g. "0 2 * * *" for daily at 2am (leave blank to disable)' />)}
            </div>
          )}

          {/* --- Tab 1: Connection --- */}
          {tab === 1 && (
            <div>
              {fieldRow('Database Type *',
                <select style={inputStyle} value={form.db_type} onChange={e => handleDbTypeChange(e.target.value as DbType)}>
                  <option value="postgresql">PostgreSQL</option>
                  <option value="mysql">MySQL / MariaDB</option>
                  <option value="oracle">Oracle</option>
                </select>
              )}
              <div className="grid grid-cols-3 gap-3 mb-3">
                <div className="col-span-2">
                  <label style={labelStyle}>Host *</label>
                  <div className="mt-1"><input style={inputStyle} value={form.host} onChange={e => set('host', e.target.value)} placeholder="192.168.1.10" /></div>
                </div>
                <div>
                  <label style={labelStyle}>Port *</label>
                  <div className="mt-1"><input style={inputStyle} type="number" value={form.port} onChange={e => set('port', e.target.value)} /></div>
                </div>
              </div>
              {fieldRow('Database Name / Service Name *', <input style={inputStyle} value={form.database_name} onChange={e => set('database_name', e.target.value)} placeholder="his_prod" />)}
              {fieldRow('Username *', <input style={inputStyle} value={form.username} onChange={e => set('username', e.target.value)} />)}
              {fieldRow(isEdit ? 'Password (leave blank to keep existing)' : 'Password *',
                <input style={inputStyle} type="password" value={form.password || ''} onChange={e => set('password', e.target.value)} placeholder={isEdit ? '••••••••' : ''} />
              )}

              {isEdit && (
                <div className="mt-4 flex items-center gap-3">
                  <button
                    onClick={handleTest}
                    disabled={testing}
                    className="btn-secondary flex items-center gap-1 text-xs"
                  >
                    {testing ? <Loader2 size={12} className="animate-spin" /> : <Database size={12} />}
                    Test Connection
                  </button>
                  {testResult && (
                    <span className="text-xs flex items-center gap-1" style={{ color: testResult.success ? 'var(--c-green)' : 'var(--c-red)' }}>
                      {testResult.success ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                      {testResult.message}
                    </span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* --- Tab 2: Query & Pagination --- */}
          {tab === 2 && (
            <div>
              <div className="mb-3">
                <label style={labelStyle}>SQL Query *</label>
                <p className="text-xs mt-0.5 mb-1" style={{ color: 'var(--c-text-sub)' }}>
                  Write a SELECT query. The service wraps it for pagination automatically.
                </p>
                <textarea
                  style={{ ...inputStyle, height: 160, resize: 'vertical', fontFamily: 'monospace', fontSize: '0.8rem' }}
                  value={form.query}
                  onChange={e => set('query', e.target.value)}
                  placeholder="SELECT item_code, store_code, txn_date, quantity FROM his_consumption WHERE txn_date >= '2024-01-01'"
                  spellCheck={false}
                />
              </div>
              {fieldRow('Page Size (rows per page)',
                <div>
                  <input style={inputStyle} type="number" min="0" value={form.page_size} onChange={e => set('page_size', e.target.value)} />
                  <p className="text-xs mt-1" style={{ color: 'var(--c-text-sub)' }}>Set to 0 to fetch all rows in one request (no pagination).</p>
                </div>
              )}
            </div>
          )}

          {/* --- Tab 3: Column Mapping --- */}
          {tab === 3 && (
            <div>
              <p className="text-xs mb-3" style={{ color: 'var(--c-text-sub)' }}>
                Map each required/optional field to the exact column name returned by your query.
                Data type: <strong style={{ color: 'var(--c-cyan)' }}>{DATA_TYPE_LABELS[form.data_type as DataType]}</strong>
              </p>
              {requiredFields.length > 0 && (
                <>
                  <p className="text-xs font-semibold mb-2" style={{ color: 'var(--c-text)' }}>Required</p>
                  {requiredFields.map(field => (
                    <div key={field} className="grid grid-cols-2 gap-3 mb-2 items-center">
                      <span className="text-xs font-mono" style={{ color: 'var(--c-cyan)' }}>{field}</span>
                      <input
                        style={inputStyle}
                        placeholder="source column name"
                        value={form.column_mapping[field] || ''}
                        onChange={e => setMapping(field, e.target.value)}
                      />
                    </div>
                  ))}
                </>
              )}
              {optionalFields.length > 0 && (
                <>
                  <p className="text-xs font-semibold mt-4 mb-2" style={{ color: 'var(--c-text-sub)' }}>Optional</p>
                  {optionalFields.map(field => (
                    <div key={field} className="grid grid-cols-2 gap-3 mb-2 items-center">
                      <span className="text-xs font-mono" style={{ color: 'var(--c-text-sub)' }}>{field}</span>
                      <input
                        style={inputStyle}
                        placeholder="source column name (optional)"
                        value={form.column_mapping[field] || ''}
                        onChange={e => setMapping(field, e.target.value)}
                      />
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-5 py-3" style={{ borderTop: '1px solid var(--c-bdr)' }}>
          <button onClick={onClose} className="btn-secondary text-xs">Cancel</button>
          <button onClick={handleSubmit} disabled={isSaving} className="btn-primary text-xs">
            {isSaving ? 'Saving…' : 'Save Config'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Run history row (expandable)
// ---------------------------------------------------------------------------
function RunHistoryPanel({ configId }: { configId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['dm-runs', configId],
    queryFn: () => getDataMiningRuns(configId, 10),
    staleTime: 10_000,
  })
  const runs: MiningRun[] = data ?? []

  if (isLoading) return <td colSpan={8} className="px-6 py-3 text-xs" style={{ color: 'var(--c-text-sub)' }}>Loading…</td>
  if (!runs.length) return <td colSpan={8} className="px-6 py-3 text-xs" style={{ color: 'var(--c-text-sub)' }}>No runs yet.</td>

  return (
    <td colSpan={8} className="px-4 py-2">
      <table className="w-full text-xs">
        <thead>
          <tr>
            {['Started', 'Duration', 'Status', 'Fetched', 'Inserted', 'Skipped', 'Error'].map(h => (
              <th key={h} className="text-left pr-4 pb-1" style={{ color: 'var(--c-text-sub)', fontWeight: 500 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {runs.map(r => (
            <tr key={r.id}>
              <td className="pr-4 py-0.5" style={{ color: 'var(--c-text)' }}>{new Date(r.started_at).toLocaleString()}</td>
              <td className="pr-4">{fmtDuration(r.started_at, r.ended_at)}</td>
              <td className="pr-4"><StatusBadge status={r.status} /></td>
              <td className="pr-4">{r.rows_fetched}</td>
              <td className="pr-4" style={{ color: 'var(--c-green)' }}>{r.rows_inserted}</td>
              <td className="pr-4" style={{ color: 'var(--c-orange)' }}>{r.rows_skipped}</td>
              <td style={{ color: 'var(--c-red)', maxWidth: 260 }}>
                {r.error_message ? <span title={r.error_message}>{r.error_message.slice(0, 80)}{r.error_message.length > 80 ? '…' : ''}</span> : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </td>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function DataMining() {
  const qc = useQueryClient()
  const [modalConfig, setModalConfig] = useState<any | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['dm-status'],
    queryFn: getDataMiningStatus,
    refetchInterval: 5_000,
    refetchIntervalInBackground: false,
    staleTime: 4_000,
  })

  const entries: StatusEntry[] = data ?? []
  const hasRunning = entries.some(e => e.config.last_run_status === 'running')

  const createMut = useMutation({
    mutationFn: createDataMiningConfig,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['dm-status'] }); setModalConfig(null) },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => updateDataMiningConfig(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['dm-status'] }); setModalConfig(null) },
  })

  const deleteMut = useMutation({
    mutationFn: deleteDataMiningConfig,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dm-status'] }),
  })

  const runMut = useMutation({
    mutationFn: runDataMining,
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ['dm-status'] }), 800),
  })

  const handleSave = (payload: any) => {
    if (modalConfig?.id) {
      updateMut.mutate({ id: modalConfig.id, data: payload })
    } else {
      createMut.mutate(payload)
    }
  }

  const handleDelete = (id: number, name: string) => {
    if (window.confirm(`Delete "${name}"? This will also remove all run history.`)) {
      deleteMut.mutate(id)
    }
  }

  const isSaving = createMut.isPending || updateMut.isPending

  return (
    <div>
      <PageHeader
        title="Data Mining"
        actions={
          <button
            onClick={() => setModalConfig({})}
            className="btn-primary flex items-center gap-1 text-xs"
          >
            <Plus size={13} /> Add Config
          </button>
        }
      >
        Pull data from external databases directly into the planning system.
        Each config has its own connection, query, and column mapping.
        {hasRunning && <span className="ml-2 badge-cyan flex items-center gap-1 inline-flex"><Loader2 size={10} className="animate-spin" />Running</span>}
      </PageHeader>

      {isLoading && <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p>}
      {isError && <p className="text-sm" style={{ color: 'var(--c-red)' }}>Failed to load data mining status.</p>}

      {!isLoading && entries.length === 0 && (
        <div className="cyber-panel text-center py-12">
          <Database size={32} style={{ color: 'var(--c-text-sub)', margin: '0 auto 0.75rem' }} />
          <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>No data mining configs yet.</p>
          <button onClick={() => setModalConfig({})} className="btn-primary text-xs mt-3 flex items-center gap-1 mx-auto">
            <Plus size={12} /> Add your first config
          </button>
        </div>
      )}

      {entries.length > 0 && (
        <div className="cyber-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="cyber-th w-8" />
                <th className="cyber-th">Name</th>
                <th className="cyber-th">Data Type</th>
                <th className="cyber-th">DB</th>
                <th className="cyber-th">Status</th>
                <th className="cyber-th">Last Run</th>
                <th className="cyber-th">Inserted / Skipped</th>
                <th className="cyber-th">Actions</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(({ config, latest_run: _latest_run }) => {
                const isExpanded = expandedId === config.id
                return (
                  <>
                    <tr key={config.id} className="cyber-tr">
                      {/* Expand toggle */}
                      <td className="px-2 py-2 text-center">
                        <button
                          onClick={() => setExpandedId(isExpanded ? null : config.id)}
                          style={{ color: 'var(--c-text-sub)', background: 'none', padding: 2 }}
                          title="Show run history"
                        >
                          {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                        </button>
                      </td>
                      <td className="px-4 py-2">
                        <div className="font-medium text-xs" style={{ color: 'var(--c-text)' }}>{config.name}</div>
                        {config.description && (
                          <div className="text-xs mt-0.5" style={{ color: 'var(--c-text-sub)', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{config.description}</div>
                        )}
                        {!config.enabled && <span className="badge-gray text-xs mt-0.5">Disabled</span>}
                      </td>
                      <td className="px-4 py-2">
                        <span className="badge-cyan">{DATA_TYPE_LABELS[config.data_type]}</span>
                      </td>
                      <td className="px-4 py-2">
                        <span className="text-xs font-mono" style={{ color: 'var(--c-text-sub)', textTransform: 'uppercase' }}>{config.db_type}</span>
                        <div className="text-xs" style={{ color: 'var(--c-text-sub)' }}>{config.host}:{config.port}</div>
                      </td>
                      <td className="px-4 py-2">
                        <StatusBadge status={config.last_run_status} />
                      </td>
                      <td className="px-4 py-2 text-xs" style={{ color: 'var(--c-text-sub)' }}>
                        {config.last_run_at ? new Date(config.last_run_at).toLocaleString() : '—'}
                        {config.schedule_cron && (
                          <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--c-purple)', fontSize: '0.68rem' }}>{config.schedule_cron}</div>
                        )}
                      </td>
                      <td className="px-4 py-2 text-xs">
                        {config.last_run_status !== 'never' ? (
                          <span>
                            <span style={{ color: 'var(--c-green)' }}>{config.last_rows_inserted ?? 0}</span>
                            {' / '}
                            <span style={{ color: 'var(--c-orange)' }}>{config.last_rows_skipped ?? 0}</span>
                          </span>
                        ) : <span style={{ color: 'var(--c-text-sub)' }}>—</span>}
                        {config.last_error && config.last_run_status === 'error' && (
                          <div className="text-xs mt-0.5" style={{ color: 'var(--c-red)', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={config.last_error}>
                            {config.last_error.slice(0, 60)}…
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => runMut.mutate(config.id)}
                            disabled={config.last_run_status === 'running' || runMut.isPending}
                            className="btn-primary text-xs px-2 py-0.5 flex items-center gap-1 disabled:opacity-40"
                            title="Run now"
                          >
                            {config.last_run_status === 'running'
                              ? <Loader2 size={10} className="animate-spin" />
                              : <Play size={10} />}
                            Run
                          </button>
                          <button
                            onClick={() => setModalConfig(config)}
                            className="btn-secondary text-xs px-2 py-0.5 flex items-center gap-1"
                            title="Edit"
                          >
                            <Pencil size={10} />
                          </button>
                          <button
                            onClick={() => handleDelete(config.id, config.name)}
                            disabled={deleteMut.isPending}
                            className="btn-secondary text-xs px-2 py-0.5 flex items-center gap-1 disabled:opacity-40"
                            title="Delete"
                            style={{ color: 'var(--c-red)' }}
                          >
                            <Trash2 size={10} />
                          </button>
                        </div>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${config.id}-runs`} style={{ background: 'rgba(var(--c-accent-rgb),0.03)', borderBottom: '1px solid var(--c-bdr)' }}>
                        <RunHistoryPanel configId={config.id} />
                      </tr>
                    )}
                  </>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {modalConfig !== null && (
        <ConfigModal
          initial={modalConfig}
          onClose={() => setModalConfig(null)}
          onSave={handleSave}
          isSaving={isSaving}
        />
      )}
    </div>
  )
}
