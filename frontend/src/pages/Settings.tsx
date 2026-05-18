import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getHospitals, getStores, getItems,
  getHospitalSettings, upsertHospitalSettings,
  getStoreSettings, upsertStoreSettings,
  getItemSettings, upsertItemSettings,
} from '../api/client'
import PageHeader from '../components/PageHeader'
import Typeahead from '../components/Typeahead'

type Tab = 'hospital' | 'store' | 'item'

export default function Settings() {
  const [tab, setTab] = useState<Tab>('hospital')
  return (
    <div>
      <PageHeader title="Settings" />
      <div className="flex gap-4 mb-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
        {(['hospital', 'store', 'item'] as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={tab === t ? 'cyber-tab-active' : 'cyber-tab'}>
            {t.charAt(0).toUpperCase() + t.slice(1)} Settings
          </button>
        ))}
      </div>
      {tab === 'hospital' && <HospitalSettings />}
      {tab === 'store' && <StoreSettings />}
      {tab === 'item' && <ItemSettings />}
    </div>
  )
}

function HospitalSettings() {
  const qc = useQueryClient()
  const [hospitalId, setHospitalId] = useState<number | ''>('')
  const [formulaErr, setFormulaErr] = useState('')
  const { data: hospitals = [] } = useQuery({ queryKey: ['hospitals'], queryFn: getHospitals })
  const { data: settings, isLoading } = useQuery({
    queryKey: ['hospitalSettings', hospitalId],
    queryFn: () => getHospitalSettings(hospitalId as number),
    enabled: hospitalId !== '',
  })

  const [form, setForm] = useState<any>({})
  const save = useMutation({
    mutationFn: () => upsertHospitalSettings(hospitalId as number, form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hospitalSettings', hospitalId] }),
    onError: (e: any) => setFormulaErr(e?.response?.data?.detail ?? 'Error saving'),
  })

  return (
    <div>
      <div className="flex gap-2 items-center mb-4">
        <label className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Hospital:</label>
        <Typeahead
          options={hospitals.map((h: any) => ({ value: String(h.id), label: h.name }))}
          value={hospitalId !== '' ? String(hospitalId) : ''}
          onChange={v => { if (v) setHospitalId(Number(v)) }}
          placeholder="Select…"
          className="w-56"
        />
      </div>
      {hospitalId !== '' && (
        isLoading ? <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p> : (
          <HospitalSettingsForm settings={settings} onFormChange={setForm} formulaErr={formulaErr} onSave={() => save.mutate()} isPending={save.isPending} />
        )
      )}
    </div>
  )
}

function HospitalSettingsForm({ settings, onFormChange, formulaErr, onSave, isPending }: any) {
  const [f, setF] = useState(() => settings ?? {})
  function update(k: string, v: any) { const nf = { ...f, [k]: v }; setF(nf); onFormChange(nf) }

  const numFields = [
    ['lookback_days', 'Lookback Days'],
    ['fsn_period_days', 'FSN Period Days'],
    ['fsn_schedule_days', 'FSN Schedule (days)'],
    ['indent_duration_days', 'Indent Duration Days'],
    ['safety_stock_pct', 'Safety Stock %'],
    ['fsn_fast_threshold', 'FSN Fast Threshold'],
    ['fsn_slow_threshold', 'FSN Slow Threshold'],
    ['reorder_level', 'Reorder Level'],
    ['min_stock', 'Min Stock'],
    ['max_stock', 'Max Stock'],
  ]

  return (
    <div className="cyber-panel p-4 max-w-xl">
      <div className="grid grid-cols-2 gap-3">
        {numFields.map(([k, label]) => (
          <div key={k}>
            <label className="form-label">{label}</label>
            <input type="number" step="any" className="form-input" value={f[k] ?? ''} onChange={e => update(k, e.target.value === '' ? null : Number(e.target.value))} />
          </div>
        ))}
      </div>
      <label className="form-label mt-3">Projection Formula</label>
      <select className="form-input w-48" value={f.projection_formula ?? 'standard'} onChange={e => update('projection_formula', e.target.value)}>
        <option value="standard">Standard</option>
        <option value="custom">Custom</option>
      </select>
      {f.projection_formula === 'custom' && (
        <>
          <label className="form-label mt-3">Custom Formula Expression</label>
          <input className="form-input font-mono text-xs" placeholder="e.g. avg_daily * indent_days * 1.1 - closing_stock" value={f.projection_formula_expr ?? ''} onChange={e => update('projection_formula_expr', e.target.value)} />
          <p className="text-xs mt-1" style={{ color: 'var(--c-text-sub)' }}>Variables: avg_daily, indent_days, closing_stock, safety_pct</p>
          {formulaErr && <p className="text-xs mt-1" style={{ color: 'var(--c-red)' }}>{formulaErr}</p>}
        </>
      )}
      <div className="flex justify-end mt-4">
        <button onClick={onSave} disabled={isPending} className="btn-primary">{isPending ? 'Saving…' : 'Save'}</button>
      </div>
    </div>
  )
}

function StoreSettings() {
  const qc = useQueryClient()
  const [storeId, setStoreId] = useState<number | ''>('')
  const { data: stores = [] } = useQuery({ queryKey: ['stores'], queryFn: () => getStores() })
  const { data: settings } = useQuery({
    queryKey: ['storeSettings', storeId],
    queryFn: () => getStoreSettings(storeId as number),
    enabled: storeId !== '',
  })
  const [form, setForm] = useState<any>({})
  const save = useMutation({
    mutationFn: () => upsertStoreSettings(storeId as number, form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['storeSettings', storeId] }),
  })

  const numFields = [
    ['indent_duration_days', 'Indent Duration Days (override)'],
    ['lookback_days', 'Lookback Days'],
    ['safety_stock_pct', 'Safety Stock %'],
    ['reorder_level', 'Reorder Level'],
    ['min_stock', 'Min Stock'],
    ['max_stock', 'Max Stock'],
  ]

  function update(k: string, v: any) { const nf = { ...form, [k]: v }; setForm(nf) }

  return (
    <div>
      <div className="flex gap-2 items-center mb-4">
        <label className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Store:</label>
        <Typeahead
          options={stores.map((s: any) => ({ value: String(s.id), label: `${s.code} — ${s.name}` }))}
          value={storeId !== '' ? String(storeId) : ''}
          onChange={v => { if (v) { setStoreId(Number(v)); setForm(settings ?? {}) } }}
          placeholder="Select…"
          className="w-60"
        />
      </div>
      {storeId !== '' && (
        <div className="cyber-panel p-4 max-w-xl">
          <div className="grid grid-cols-2 gap-3">
            {numFields.map(([k, label]) => (
              <div key={k}>
                <label className="form-label">{label}</label>
                <input type="number" step="any" className="form-input" value={form[k] ?? ''} onChange={e => update(k, e.target.value === '' ? null : Number(e.target.value))} />
              </div>
            ))}
          </div>
          <div className="flex justify-end mt-4">
            <button onClick={() => save.mutate()} disabled={save.isPending} className="btn-primary">{save.isPending ? 'Saving…' : 'Save'}</button>
          </div>
        </div>
      )}
    </div>
  )
}

function ItemSettings() {
  const qc = useQueryClient()
  const [itemId, setItemId] = useState<number | ''>('')
  const { data: items = [] } = useQuery({ queryKey: ['items'], queryFn: () => getItems() })
  const { data: settings } = useQuery({
    queryKey: ['itemSettings', itemId],
    queryFn: () => getItemSettings(itemId as number),
    enabled: itemId !== '',
  })
  const [form, setForm] = useState<any>({})
  const save = useMutation({
    mutationFn: () => upsertItemSettings(itemId as number, form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['itemSettings', itemId] }),
  })

  function update(k: string, v: any) { setForm((f: any) => ({ ...f, [k]: v })) }

  const numFields = [
    ['safety_stock_pct', 'Safety Stock %'],
    ['lookback_days', 'Lookback Days'],
    ['reorder_level', 'Reorder Level'],
    ['min_stock', 'Min Stock'],
    ['max_stock', 'Max Stock'],
  ]

  return (
    <div>
      <div className="flex gap-2 items-center mb-4">
        <label className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Item:</label>
        <Typeahead
          options={items.map((i: any) => ({ value: String(i.id), label: `${i.code} — ${i.name}` }))}
          value={itemId !== '' ? String(itemId) : ''}
          onChange={v => { if (v) { setItemId(Number(v)); setForm(settings ?? {}) } }}
          placeholder="Select…"
          className="w-72"
        />
      </div>
      {itemId !== '' && (
        <div className="cyber-panel p-4 max-w-lg">
          <div className="grid grid-cols-2 gap-3">
            {numFields.map(([k, label]) => (
              <div key={k}>
                <label className="form-label">{label}</label>
                <input type="number" step="any" className="form-input" value={form[k] ?? ''} onChange={e => update(k, e.target.value === '' ? null : Number(e.target.value))} />
              </div>
            ))}
          </div>
          <div className="flex justify-end mt-4">
            <button onClick={() => save.mutate()} disabled={save.isPending} className="btn-primary">{save.isPending ? 'Saving…' : 'Save'}</button>
          </div>
        </div>
      )}
    </div>
  )
}
