import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSchedulerStatus, runJobNow, runAllJobsNow } from '../api/client'
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
    </div>
  )
}

