import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getHospitals, getStores, getItems, getConsumptionAnalysis } from '../api/client'
import PageHeader from '../components/PageHeader'
import Typeahead from '../components/Typeahead'

function StatCell({ label, value, unit = '', color = 'var(--c-cyan)' }: {
  label: string; value: string | number; unit?: string; color?: string
}) {
  return (
    <div className="cyber-panel p-4 flex flex-col gap-1">
      <span className="text-xs" style={{ color: 'var(--c-text-sub)' }}>{label}</span>
      <span className="text-2xl font-bold font-mono" style={{ color }}>
        {typeof value === 'number' ? value.toFixed(2) : value}
        {unit && <span className="text-sm font-normal ml-1" style={{ color: 'var(--c-text-sub)' }}>{unit}</span>}
      </span>
    </div>
  )
}

export default function ConsumptionAnalysis() {
  const today = new Date().toISOString().slice(0, 10)

  const [hospitalId, setHospitalId] = useState('')
  const [storeId, setStoreId] = useState('')
  const [itemId, setItemId] = useState('')
  const [asOf, setAsOf] = useState(today)
  const [lookbackDays, setLookbackDays] = useState('')
  const [submitted, setSubmitted] = useState<{
    item_id: number; store_id: number; as_of: string; lookback_days?: number
  } | null>(null)

  const { data: hospitals = [] } = useQuery({ queryKey: ['hospitals'], queryFn: getHospitals })
  const { data: stores = [] } = useQuery({ queryKey: ['stores'], queryFn: () => getStores() })
  const { data: items = [] } = useQuery({ queryKey: ['items'], queryFn: () => getItems() })

  const filteredStores = useMemo(
    () => hospitalId ? stores.filter((s: any) => String(s.hospital_id) === hospitalId) : stores,
    [stores, hospitalId]
  )

  const hospitalOptions = useMemo(() => hospitals.map((h: any) => ({ value: String(h.id), label: h.name })), [hospitals])
  const storeOptions = useMemo(() => filteredStores.map((s: any) => ({ value: String(s.id), label: `${s.code} — ${s.name}` })), [filteredStores])
  const itemOptions = useMemo(() => items.map((i: any) => ({ value: String(i.id), label: `${i.code} — ${i.name}` })), [items])

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['consumption-analysis', submitted],
    queryFn: () => getConsumptionAnalysis({
      item_id: submitted!.item_id,
      store_id: submitted!.store_id,
      as_of: submitted!.as_of,
      lookback_days: submitted!.lookback_days,
    }),
    enabled: !!submitted,
  })

  function handleAnalyse() {
    if (!itemId || !storeId) return
    setSubmitted({
      item_id: Number(itemId),
      store_id: Number(storeId),
      as_of: asOf,
      lookback_days: lookbackDays ? Number(lookbackDays) : undefined,
    })
  }

  return (
    <div>
      <PageHeader title="Consumption Analysis" />

      {/* Filters */}
      <div className="cyber-panel p-4 mb-6">
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
          <div>
            <label className="form-label">Hospital</label>
            <Typeahead
              options={hospitalOptions}
              value={hospitalId}
              onChange={v => { setHospitalId(v); setStoreId('') }}
              placeholder="Filter by hospital…"
            />
          </div>
          <div>
            <label className="form-label">Store *</label>
            <Typeahead
              options={storeOptions}
              value={storeId}
              onChange={setStoreId}
              placeholder="Select store…"
            />
          </div>
          <div>
            <label className="form-label">Item *</label>
            <Typeahead
              options={itemOptions}
              value={itemId}
              onChange={setItemId}
              placeholder="Select item…"
            />
          </div>
          <div>
            <label className="form-label">As Of Date</label>
            <input
              type="date"
              className="form-input"
              value={asOf}
              onChange={e => setAsOf(e.target.value)}
            />
          </div>
          <div>
            <label className="form-label">Lookback Days</label>
            <input
              type="number"
              min={1}
              step={1}
              className="form-input"
              placeholder="Default: hospital setting"
              value={lookbackDays}
              onChange={e => setLookbackDays(e.target.value)}
            />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            className="btn-primary"
            disabled={!itemId || !storeId || isLoading}
            onClick={handleAnalyse}
          >
            {isLoading ? 'Loading…' : 'Analyse'}
          </button>
          {submitted && (
            <span className="text-xs" style={{ color: 'var(--c-text-sub)' }}>
              {data ? `${data.item_code} — ${data.item_name} @ ${data.store_name}, ${data.lookback_days}d window ending ${data.as_of}` : ''}
            </span>
          )}
        </div>
        {isError && (
          <p className="text-sm mt-2" style={{ color: 'var(--c-red)' }}>
            {(error as any)?.message ?? 'Failed to load analysis'}
          </p>
        )}
      </div>

      {data && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <StatCell label="Baseline Avg Daily" value={data.baseline_avg_daily} unit="units/day" />
            <StatCell
              label={`Weighted Rolling Avg${data.rolling_bucket_days > 1 ? ` (${data.rolling_bucket_days}d buckets)` : ''}`}
              value={data.weighted_rolling_avg_daily}
              unit="units/day"
              color="var(--c-purple)"
            />
            <StatCell
              label="Trend-Adjusted Avg"
              value={data.trend_adjusted_avg_daily}
              unit="units/day"
              color="var(--c-orange)"
            />
            <StatCell label="Total Consumption" value={data.total_consumption} unit="units" color="var(--c-green)" />
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <StatCell label="Window (days)" value={data.lookback_days} color="var(--c-text)" />
            <StatCell label="Active Days" value={`${data.active_days} / ${data.lookback_days}`} color="var(--c-text)" />
            <StatCell label="Bucket Size" value={data.rolling_bucket_days} unit="days" color="var(--c-text)" />
            <StatCell label="Weight Factor" value={data.rolling_recent_weight_factor} color="var(--c-text)" />
          </div>

          {/* Bucket breakdown */}
          {data.bucket_series.length > 0 && (
            <div className="cyber-panel p-4 mb-6">
              <h2 className="cyber-section-title mb-3">
                Bucket Breakdown
                <span className="ml-2 text-xs font-normal" style={{ color: 'var(--c-text-sub)' }}>
                  {data.bucket_series.length} buckets × {data.rolling_bucket_days} days
                </span>
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr>
                      <th className="cyber-th">#</th>
                      <th className="cyber-th">Period</th>
                      <th className="cyber-th text-right">Total</th>
                      <th className="cyber-th text-right">Avg Daily</th>
                      <th className="cyber-th text-right">Weight</th>
                      <th className="cyber-th text-right">Weighted Contrib.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.bucket_series.map((b: any) => {
                      const contrib = b.avg_daily * b.weight
                      const totalW = data.bucket_series.reduce((s: number, x: any) => s + x.weight, 0)
                      const pct = totalW > 0 ? (b.weight / totalW) * 100 : 0
                      return (
                        <tr key={b.bucket_index} className="cyber-tr">
                          <td className="px-4 py-2" style={{ color: 'var(--c-text-sub)' }}>
                            {b.bucket_index + 1}
                          </td>
                          <td className="px-4 py-2 font-mono" style={{ color: 'var(--c-text)' }}>
                            {b.start_date} → {b.end_date}
                          </td>
                          <td className="px-4 py-2 text-right font-mono">{b.total.toFixed(2)}</td>
                          <td className="px-4 py-2 text-right font-mono" style={{ color: 'var(--c-cyan)' }}>
                            {b.avg_daily.toFixed(4)}
                          </td>
                          <td className="px-4 py-2 text-right">
                            <span style={{ color: 'var(--c-purple)' }}>{b.weight.toFixed(3)}</span>
                            <span className="ml-1 text-xs" style={{ color: 'var(--c-text-sub)' }}>
                              ({pct.toFixed(1)}%)
                            </span>
                          </td>
                          <td className="px-4 py-2 text-right font-mono" style={{ color: 'var(--c-orange)' }}>
                            {contrib.toFixed(4)}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                  <tfoot>
                    <tr style={{ borderTop: '1px solid var(--c-border)' }}>
                      <td colSpan={3} className="px-4 py-2 text-right text-xs" style={{ color: 'var(--c-text-sub)' }}>
                        Weighted Avg =
                      </td>
                      <td colSpan={3} className="px-4 py-2 font-mono font-bold" style={{ color: 'var(--c-purple)' }}>
                        {data.weighted_rolling_avg_daily.toFixed(4)} units/day
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          )}

          {/* Daily series */}
          <div className="cyber-panel p-4">
            <h2 className="cyber-section-title mb-3">
              Daily Consumption
              <span className="ml-2 text-xs font-normal" style={{ color: 'var(--c-text-sub)' }}>
                {data.daily_series.length} days
              </span>
            </h2>
            <div className="overflow-x-auto max-h-96 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0" style={{ background: 'var(--c-panel)' }}>
                  <tr>
                    <th className="cyber-th">Date</th>
                    <th className="cyber-th text-right">Quantity</th>
                    <th className="cyber-th text-right">Cumulative</th>
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    let cumulative = 0
                    return data.daily_series.map((d: any) => {
                      cumulative += d.quantity
                      return (
                        <tr key={d.date} className="cyber-tr">
                          <td className="px-4 py-1.5 font-mono" style={{ color: 'var(--c-text-sub)' }}>{d.date}</td>
                          <td
                            className="px-4 py-1.5 text-right font-mono"
                            style={{ color: d.quantity > 0 ? 'var(--c-cyan)' : 'var(--c-text-sub)' }}
                          >
                            {d.quantity > 0 ? d.quantity.toFixed(2) : '—'}
                          </td>
                          <td className="px-4 py-1.5 text-right font-mono" style={{ color: 'var(--c-text)' }}>
                            {cumulative.toFixed(2)}
                          </td>
                        </tr>
                      )
                    })
                  })()}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!data && !isLoading && (
        <div className="cyber-panel p-8 text-center" style={{ color: 'var(--c-text-sub)' }}>
          <p className="text-sm">Select a store and item, then click Analyse to see consumption data.</p>
        </div>
      )}
    </div>
  )
}
