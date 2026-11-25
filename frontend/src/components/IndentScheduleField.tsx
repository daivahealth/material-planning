import { useQuery } from '@tanstack/react-query'
import { previewIndentSchedule } from '../api/client'
import { useDebounced } from '../hooks/useDebounced'

/** Presets covering what the feature was asked for: daily, and particular
 *  days of the week. Anything else can still be typed. */
const PRESETS: { label: string; cron: string }[] = [
  { label: 'Daily 06:00',   cron: '0 6 * * *' },
  { label: 'Weekdays 06:00', cron: '0 6 * * MON-FRI' },
  { label: 'Mon/Wed/Fri 06:00', cron: '0 6 * * MON,WED,FRI' },
  { label: 'Mondays 06:00', cron: '0 6 * * MON' },
]

interface Props {
  value?: string | null
  onChange: (v: string | null) => void
  /** Hospital level is mandatory; store level is an override that may be blank. */
  level: 'hospital' | 'store'
  /** What a blank store field will inherit, for the hint text. */
  inherited?: string | null
}

function fmt(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    weekday: 'short', day: '2-digit', month: 'short',
    hour: '2-digit', minute: '2-digit',
  })
}

/**
 * Cron field for the per-store indent schedule, with a live server-rendered
 * preview.
 *
 * The preview is not decoration. Two properties of the mechanism are
 * invisible in a cron expression and would otherwise be reported as bugs:
 *   * the evaluating job ticks hourly, so a non-zero minute is acted on by the
 *     FOLLOWING hour (and 23:30 by 00:00 the next day);
 *   * a schedule may fire at most once a day, because a store dispatches once
 *     per day whatever the cron says.
 * Both come back from the same validator the save path uses.
 */
export default function IndentScheduleField({ value, onChange, level, inherited }: Props) {
  const typed = (value ?? '').trim()
  const debounced = useDebounced(typed, 300)

  const { data: preview } = useQuery({
    queryKey: ['indentSchedulePreview', debounced],
    queryFn: () => previewIndentSchedule(debounced),
    enabled: debounced !== '',
    retry: false,
  })

  const blank = typed === ''
  const inheritedHint = level === 'store' && blank

  return (
    <div className="mt-3">
      <label className="form-label">
        Indent Schedule{level === 'hospital' ? ' (required)' : ' (override)'}
      </label>
      <input
        className="form-input font-mono w-72"
        placeholder={level === 'hospital' ? '0 6 * * *' : '— Inherit from hospital —'}
        value={value ?? ''}
        onChange={e => onChange(e.target.value === '' ? null : e.target.value)}
      />

      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <span className="text-xs" style={{ color: 'var(--c-text-sub)' }}>Presets:</span>
        {PRESETS.map(p => (
          <button key={p.cron} type="button" onClick={() => onChange(p.cron)}
            className="btn-secondary" style={{ padding: '2px 8px', fontSize: '0.7rem' }}>
            {p.label}
          </button>
        ))}
        {level === 'store' && !blank && (
          <button type="button" onClick={() => onChange(null)}
            className="text-xs" style={{ color: 'var(--c-cyan)', background: 'none', border: 'none', cursor: 'pointer' }}>
            Clear (inherit)
          </button>
        )}
      </div>

      {inheritedHint && (
        <p className="text-xs mt-1" style={{ color: 'var(--c-text-sub)' }}>
          Inheriting from hospital{inherited ? <>: <span className="font-mono">{inherited}</span></> : ''}.
        </p>
      )}

      {!blank && preview && !preview.valid && (
        <p className="text-xs mt-1" style={{ color: 'var(--c-red)' }}>{preview.error}</p>
      )}

      {!blank && preview?.valid && (
        <div className="text-xs mt-1" style={{ color: 'var(--c-text-sub)' }}>
          <p style={{ color: 'var(--c-cyan)' }}>{preview.description}</p>
          {preview.rounded_up && (
            <p style={{ color: 'var(--c-orange)' }}>
              Evaluated hourly, so this is acted on at {String(preview.effective_hour).padStart(2, '0')}:00 —
              the minute is rounded up to the next hour.
            </p>
          )}
          <p>Next: {(preview.run_times ?? []).map(fmt).join('  ·  ')}</p>
        </div>
      )}

      <p className="text-xs mt-1" style={{ color: 'var(--c-text-sub)' }}>
        5-field cron. Evaluated by the hourly Outbound Dispatch run, so only the hour is
        honoured and a schedule may fire at most once a day. A missed run (downtime) is
        skipped, not caught up.
      </p>
    </div>
  )
}
