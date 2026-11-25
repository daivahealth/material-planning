import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSchedulerStatus, runJobNow, runAllJobsNow, getStoreIndentSchedules } from '../api/client'
import PageHeader from '../components/PageHeader'
import TruncText from '../components/TruncText'
import { Clock, CheckCircle, XCircle, Play } from 'lucide-react'

export default function Scheduler() {
  const qc = useQueryClient()
  const [runningJob, setRunningJob] = useState<string | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['scheduler'],
    queryFn: getSchedulerStatus,
    refetchInterval: 60_000,       // poll every 60s (was 30s)
    refetchIntervalInBackground: false, // only poll when tab is active
    staleTime: 30_000,
  })

  const runJob = useMutation({
    mutationFn: (job_id: string) => { setRunningJob(job_id); return runJobNow(job_id) },
    onSuccess: () => { setRunningJob(null); setTimeout(() => qc.invalidateQueries({ queryKey: ['scheduler'] }), 1000) },
    onError: () => setRunningJob(null),
  })

  const runAll = useMutation({
    mutationFn: runAllJobsNow,
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ['scheduler'] }), 1000),
  })

  const jobs = data?.jobs ?? []

  return (
    <div>
      <PageHeader title="Scheduler" actions={
        <div className="flex gap-2">
          <button
            onClick={() => runAll.mutate()}
            disabled={runAll.isPending}
            className="btn-primary flex items-center gap-1"
          >
            <Play size={14} /> {runAll.isPending ? 'Triggering…' : 'Run All Now'}
          </button>
          <button onClick={() => refetch()} className="btn-secondary flex items-center gap-1">
            <Clock size={14} /> Refresh
          </button>
        </div>
      }>
        Auto-refreshes every 30 seconds. Shows all APScheduler jobs (indent per store + FSN per hospital).
      </PageHeader>

      {isLoading && <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p>}
      {isError && <p className="text-sm" style={{ color: 'var(--c-red)' }}>Failed to load scheduler status.</p>}

      {!isLoading && (
        <div className="cyber-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="cyber-th">Job ID</th>
                <th className="cyber-th">Type</th>
                <th className="cyber-th">Next Run</th>
                <th className="cyber-th">Trigger</th>
                <th className="cyber-th">Status</th>
                <th className="cyber-th">Action</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j: any) => {
                const isIndent = j.job_id?.startsWith('indent_store_')
                const isFSN = j.job_id?.startsWith('fsn_hospital_')
                const type = isIndent ? 'Indent' : isFSN ? 'FSN' : 'Other'
                const typeBadge = isIndent ? 'badge-cyan' : isFSN ? 'badge-purple' : 'badge-gray'
                const nextRun = j.next_run_time ? new Date(j.next_run_time) : null
                const isPast = nextRun && nextRun < new Date()
                const isRunning = runningJob === j.job_id
                return (
                  <tr key={j.job_id} className="cyber-tr">
                    <td className="px-4 py-2 font-mono text-xs"><TruncText text={j.job_id} style={{ color: 'var(--c-cyan)' }} mono /></td>
                    <td className="px-4 py-2"><span className={typeBadge}>{type}</span></td>
                    <td className="px-4 py-2">
                      {nextRun ? (
                        <span style={{ color: isPast ? 'var(--c-orange)' : 'var(--c-text)' }}>
                          {nextRun.toLocaleString()}
                        </span>
                      ) : <span style={{ color: 'var(--c-text-sub)' }}>—</span>}
                    </td>
                    <td className="px-4 py-2 text-xs"><TruncText text={j.trigger} style={{ color: 'var(--c-text-sub)' }} /></td>
                    <td className="px-4 py-2">
                      {isPast
                        ? <XCircle size={14} style={{ color: 'var(--c-orange)' }} />
                        : <CheckCircle size={14} style={{ color: 'var(--c-green)' }} />
                      }
                    </td>
                    <td className="px-4 py-2">
                      <button
                        onClick={() => runJob.mutate(j.job_id)}
                        disabled={isRunning || runJob.isPending}
                        className="btn-primary text-xs px-2 py-0.5 disabled:opacity-40"
                      >
                        <Play size={11} /> {isRunning ? 'Running…' : 'Run Now'}
                      </button>
                    </td>
                  </tr>
                )
              })}
              {jobs.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-sm" style={{ color: 'var(--c-text-sub)' }}>No scheduler jobs found.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      <StoreIndentSchedules />
    </div>
  )
}

/**
 * Per-store indent schedules.
 *
 * Deliberately a separate table from the one above: these are NOT APScheduler
 * jobs. The schedule is a cron expression stored per store and evaluated by the
 * hourly Outbound Dispatch run, which is why a store never appears in the job
 * list however it is configured.
 */
function StoreIndentSchedules() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['storeIndentSchedules'],
    queryFn: getStoreIndentSchedules,
    staleTime: 30_000,
    retry: false,
  })
  const rows = (data?.stores ?? []) as any[]
  const warning = data?.outbound?.warning

  return (
    <div className="mt-8">
      <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--c-text)' }}>
        Store Indent Schedules
      </h3>
      <p className="text-xs mb-2" style={{ color: 'var(--c-text-sub)' }}>
        Evaluated by the hourly <strong>Outbound Dispatch</strong> run, not registered as jobs —
        so nothing here appears in the table above. Edit a schedule in Settings → Hospital (the
        default) or Settings → Store (the override).
      </p>
      {warning && (
        <p className="text-xs mb-2" style={{ color: 'var(--c-orange)' }}>⚠ {warning}</p>
      )}
      {isLoading && <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p>}
      {isError && <p className="text-sm" style={{ color: 'var(--c-red)' }}>Failed to load store schedules.</p>}
      {!isLoading && !isError && (
        <div className="cyber-panel overflow-hidden overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className="cyber-th">Store</th>
                <th className="cyber-th">Type</th>
                <th className="cyber-th">Schedule</th>
                <th className="cyber-th">From</th>
                <th className="cyber-th">Next Run</th>
                <th className="cyber-th">Last Fire</th>
                <th className="cyber-th">Last Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.store_id} className="cyber-tr">
                  <td className="px-4 py-2">
                    <span className="font-mono" style={{ color: 'var(--c-cyan)' }}>{r.store_code}</span>
                    <span style={{ color: 'var(--c-text-sub)' }}> · {r.store_name}</span>
                  </td>
                  <td className="px-4 py-2">
                    <span className={r.request_type === 'purchase_request' ? 'badge-purple' : 'badge-cyan'}>
                      {r.request_type === 'purchase_request' ? 'PR' : 'Indent'}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <span className="font-mono">{r.cron}</span>
                    <span style={{ color: 'var(--c-text-sub)' }}> — {r.description}</span>
                  </td>
                  <td className="px-4 py-2">
                    <span className={r.source === 'store' ? 'badge-cyan' : 'badge-gray'}>{r.source}</span>
                  </td>
                  <td className="px-4 py-2">
                    {r.next_run_at ? new Date(r.next_run_at).toLocaleString()
                      : <span style={{ color: 'var(--c-text-sub)' }}>—</span>}
                  </td>
                  <td className="px-4 py-2" style={{ color: 'var(--c-text-sub)' }}>
                    {r.last_indent_fire_at ? new Date(r.last_indent_fire_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-2">
                    {r.last_indent_run_status
                      ? <span title={r.last_indent_error || ''} style={{
                          color: r.last_indent_run_status === 'failed' ? 'var(--c-red)' : 'var(--c-green)',
                        }}>{r.last_indent_run_status}</span>
                      : <span style={{ color: 'var(--c-text-sub)' }}>never run</span>}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-6 text-center" style={{ color: 'var(--c-text-sub)' }}>
                  No stores.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

