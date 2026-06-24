import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getHospitals, getStores, getItems, getItemCategories, getItemGroups,
  getHospitalSettings, upsertHospitalSettings,
  getStoreSettings, upsertStoreSettings,
  getItemSettings, upsertItemSettings,
  getCategorySettings, upsertCategorySettings,
  getGroupSettings, upsertGroupSettings,
  getItemStoreSettings, upsertItemStoreSettings,
} from '../api/client'
import PageHeader from '../components/PageHeader'
import Typeahead from '../components/Typeahead'

type Tab = 'hospital' | 'store' | 'item' | 'category' | 'group' | 'item-store'

const TABS: { id: Tab; label: string }[] = [
  { id: 'hospital',   label: 'Hospital' },
  { id: 'store',      label: 'Store' },
  { id: 'item',       label: 'Item' },
  { id: 'category',   label: 'Category' },
  { id: 'group',      label: 'Group' },
  { id: 'item-store', label: 'Item × Store' },
]

export default function Settings() {
  const [tab, setTab] = useState<Tab>('hospital')
  return (
    <div>
      <PageHeader title="Settings" />
      <p className="text-xs mb-3" style={{ color: 'var(--c-text-sub)' }}>
        Resolution order (highest → lowest):&nbsp;
        <strong style={{ color: 'var(--c-cyan)' }}>Item × Store</strong>
        {' → '}<strong>Item</strong>{' → '}<strong>Category</strong>
        {' → '}<strong>Group</strong>{' → '}<strong>Store</strong>{' → '}<strong>Hospital</strong>
      </p>
      <div className="flex flex-wrap gap-2 mb-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)', paddingBottom: '0.5rem' }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={tab === t.id ? 'cyber-tab-active' : 'cyber-tab'}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'hospital'   && <HospitalSettingsPanel />}
      {tab === 'store'      && <StoreSettingsPanel />}
      {tab === 'item'       && <ItemSettingsPanel />}
      {tab === 'category'   && <CategorySettingsPanel />}
      {tab === 'group'      && <GroupSettingsPanel />}
      {tab === 'item-store' && <ItemStoreSettingsPanel />}
    </div>
  )
}

// ─────────────────────────────────────────────
// Shared helpers
// ─────────────────────────────────────────────
function NumField({ label, field, form, update, hint, step = 'any', min }: {
  label: string; field: string; form: any; update: (k: string, v: any) => void
  hint?: string; step?: string; min?: number
}) {
  return (
    <div>
      <label className="form-label">{label}</label>
      <input
        type="number" step={step} min={min} className="form-input"
        value={form[field] ?? ''}
        onChange={e => update(field, e.target.value === '' ? null : Number(e.target.value))}
      />
      {hint && <p className="text-xs mt-0.5" style={{ color: 'var(--c-text-sub)' }}>{hint}</p>}
    </div>
  )
}

function SaveRow({ onSave, isPending }: { onSave: () => void; isPending: boolean }) {
  return (
    <div className="flex justify-end mt-4">
      <button onClick={onSave} disabled={isPending} className="btn-primary">
        {isPending ? 'Saving…' : 'Save'}
      </button>
    </div>
  )
}

function StockFields({ form, update }: { form: any; update: (k: string, v: any) => void }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <NumField label="Indent Duration Days" field="indent_duration_days" form={form} update={update} min={1} step="1" />
      <NumField label="Safety Stock (Days)"  field="safety_stock_days"    form={form} update={update} min={0}
        hint="Days of demand as buffer" />
      <NumField label="Reorder Level" field="reorder_level" form={form} update={update} />
      <NumField label="Min Stock"     field="min_stock"     form={form} update={update} />
      <NumField label="Max Stock"     field="max_stock"     form={form} update={update} />
    </div>
  )
}

// ─────────────────────────────────────────────
// Hospital Settings
// ─────────────────────────────────────────────
function HospitalSettingsPanel() {
  const qc = useQueryClient()
  const [hospitalId, setHospitalId] = useState<number | ''>('')
  const [formulaErr, setFormulaErr] = useState('')
  const [form, setForm] = useState<any>({})

  const { data: hospitals = [] } = useQuery({ queryKey: ['hospitals'], queryFn: getHospitals })
  const { data: settings } = useQuery({
    queryKey: ['hospitalSettings', hospitalId],
    queryFn: () => getHospitalSettings(hospitalId as number),
    enabled: hospitalId !== '',
  })

  useEffect(() => { if (settings !== undefined) setForm(settings) }, [settings])

  const save = useMutation({
    mutationFn: () => upsertHospitalSettings(hospitalId as number, form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hospitalSettings', hospitalId] }),
    onError: (e: any) => setFormulaErr(e?.response?.data?.detail ?? 'Error saving'),
  })

  function update(k: string, v: any) { setForm((f: any) => ({ ...f, [k]: v })) }

  return (
    <div>
      <div className="flex gap-2 items-center mb-4">
        <label className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Hospital:</label>
        <Typeahead
          options={hospitals.map((h: any) => ({ value: String(h.id), label: h.name }))}
          value={hospitalId !== '' ? String(hospitalId) : ''}
          onChange={v => { if (v) { setHospitalId(Number(v)); setForm({}) } }}
          placeholder="Select…" className="w-56"
        />
      </div>
      {hospitalId !== '' && (
        <div className="cyber-panel p-4 max-w-xl">
          <p className="text-xs mb-3" style={{ color: 'var(--c-text-sub)' }}>
            Hospital-level defaults — lowest priority, apply when no other level overrides.
          </p>
          <label className="inline-flex items-center gap-2 mb-3 text-sm" style={{ color: 'var(--c-text)' }}>
            <input type="checkbox" checked={form.planning_enabled ?? true}
              onChange={e => update('planning_enabled', e.target.checked)} />
            Planning Enabled
          </label>
          <div className="grid grid-cols-2 gap-3">
            <NumField label="Lookback Days"        field="lookback_days"        form={form} update={update} min={1} step="1" />
            <NumField label="FSN Period Days"      field="fsn_period_days"      form={form} update={update} min={1} step="1" />
            <NumField label="FSN Schedule (Days)"  field="fsn_schedule_days"    form={form} update={update} min={1} step="1" />
            <NumField label="Indent Duration Days" field="indent_duration_days" form={form} update={update} min={1} step="1" />
            <NumField label="Safety Stock (Days)"  field="safety_stock_days"    form={form} update={update} min={0}
              hint="Days of demand to hold as buffer" />
            <NumField label="Reorder Level"        field="reorder_level"        form={form} update={update} />
            <NumField label="Min Stock"            field="min_stock"            form={form} update={update} />
            <NumField label="Max Stock"            field="max_stock"            form={form} update={update} />
            <NumField label="FSN Fast Threshold"   field="fsn_fast_threshold"   form={form} update={update} />
            <NumField label="FSN Slow Threshold"   field="fsn_slow_threshold"   form={form} update={update} />
          </div>

          <label className="form-label mt-3">Forecast Method</label>
          <select className="form-input w-72" value={form.forecast_method ?? 'baseline_avg'}
            onChange={e => update('forecast_method', e.target.value)}>
            <option value="baseline_avg">Baseline Average</option>
            <option value="weighted_rolling">Weighted Rolling Average</option>
            <option value="trend_adjusted">Trend Adjusted</option>
          </select>

          {(form.forecast_method === 'weighted_rolling' || form.forecast_method === 'trend_adjusted') && (
            <div className="grid grid-cols-2 gap-3 mt-3">
              {form.forecast_method === 'weighted_rolling' && (
                <>
                  <NumField label="Recent Weight Factor" field="rolling_recent_weight_factor"
                    form={form} update={update} min={1} />
                  <NumField label="Bucket Days" field="rolling_bucket_days"
                    form={form} update={update} min={1} step="1" />
                </>
              )}
              {form.forecast_method === 'trend_adjusted' && (
                <NumField label="Trend Min Points" field="trend_min_points"
                  form={form} update={update} min={2} step="1" />
              )}
            </div>
          )}

          <label className="form-label mt-3">Projection Formula</label>
          <select className="form-input w-48" value={form.projection_formula ?? 'standard'}
            onChange={e => update('projection_formula', e.target.value)}>
            <option value="standard">Standard</option>
            <option value="custom">Custom</option>
          </select>
          {form.projection_formula === 'custom' && (
            <>
              <label className="form-label mt-3">Custom Formula Expression</label>
              <input className="form-input font-mono text-xs"
                placeholder="e.g. avg_daily * indent_days * 1.1 - closing_stock"
                value={form.projection_formula_expr ?? ''}
                onChange={e => update('projection_formula_expr', e.target.value)} />
              <p className="text-xs mt-1" style={{ color: 'var(--c-text-sub)' }}>
                Variables: avg_daily, indent_days, closing_stock, safety_pct, open_indent_qty, lead_time_days, safety_days, target_stock
              </p>
              {formulaErr && <p className="text-xs mt-1" style={{ color: 'var(--c-red)' }}>{formulaErr}</p>}
            </>
          )}
          <SaveRow onSave={() => save.mutate()} isPending={save.isPending} />
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────
// Store Settings
// ─────────────────────────────────────────────
function StoreSettingsPanel() {
  const qc = useQueryClient()
  const [storeId, setStoreId] = useState<number | ''>('')
  const [form, setForm] = useState<any>({})

  const { data: stores = [] } = useQuery({ queryKey: ['stores'], queryFn: () => getStores() })
  const { data: settings } = useQuery({
    queryKey: ['storeSettings', storeId],
    queryFn: () => getStoreSettings(storeId as number),
    enabled: storeId !== '',
  })

  useEffect(() => { if (settings !== undefined) setForm(settings) }, [settings])

  const save = useMutation({
    mutationFn: () => upsertStoreSettings(storeId as number, form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['storeSettings', storeId] }),
  })

  function update(k: string, v: any) { setForm((f: any) => ({ ...f, [k]: v })) }

  return (
    <div>
      <div className="flex gap-2 items-center mb-4">
        <label className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Store:</label>
        <Typeahead
          options={stores.map((s: any) => ({ value: String(s.id), label: `${s.code} — ${s.name}` }))}
          value={storeId !== '' ? String(storeId) : ''}
          onChange={v => { if (v) { setStoreId(Number(v)); setForm({}) } }}
          placeholder="Select…" className="w-60"
        />
      </div>
      {storeId !== '' && (
        <div className="cyber-panel p-4 max-w-xl">
          <p className="text-xs mb-3" style={{ color: 'var(--c-text-sub)' }}>
            Store-level settings override hospital defaults. Leave blank to inherit.
          </p>
          <label className="inline-flex items-center gap-2 mb-3 text-sm" style={{ color: 'var(--c-text)' }}>
            <input type="checkbox" checked={form.planning_enabled ?? true}
              onChange={e => update('planning_enabled', e.target.checked)} />
            Planning Enabled
          </label>
          <div className="grid grid-cols-2 gap-3">
            <NumField label="Lookback Days"        field="lookback_days"        form={form} update={update} min={1} step="1" />
            <NumField label="Indent Duration Days" field="indent_duration_days" form={form} update={update} min={1} step="1" />
          </div>

          <label className="form-label mt-3">Forecast Method (override)</label>
          <select className="form-input w-72"
            value={form.forecast_method ?? ''}
            onChange={e => update('forecast_method', e.target.value || null)}>
            <option value="">— Inherit from Hospital —</option>
            <option value="baseline_avg">Baseline Average</option>
            <option value="weighted_rolling">Weighted Rolling Average</option>
            <option value="trend_adjusted">Trend Adjusted</option>
          </select>

          {form.forecast_method === 'weighted_rolling' && (
            <div className="grid grid-cols-2 gap-3 mt-3">
              <NumField label="Recent Weight Factor" field="rolling_recent_weight_factor"
                form={form} update={update} min={1} hint="≥ 1.0" />
              <NumField label="Bucket Days" field="rolling_bucket_days"
                form={form} update={update} min={1} step="1" />
            </div>
          )}
          <SaveRow onSave={() => save.mutate()} isPending={save.isPending} />
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────
// Item Settings
// ─────────────────────────────────────────────
function ItemSettingsPanel() {
  const qc = useQueryClient()
  const [itemId, setItemId] = useState<number | ''>('')
  const [form, setForm] = useState<any>({})

  const { data: items = [] } = useQuery({ queryKey: ['items'], queryFn: () => getItems() })
  const { data: settings } = useQuery({
    queryKey: ['itemSettings', itemId],
    queryFn: () => getItemSettings(itemId as number),
    enabled: itemId !== '',
  })

  useEffect(() => { if (settings !== undefined) setForm(settings) }, [settings])

  const save = useMutation({
    mutationFn: () => upsertItemSettings(itemId as number, form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['itemSettings', itemId] }),
  })

  function update(k: string, v: any) { setForm((f: any) => ({ ...f, [k]: v })) }

  return (
    <div>
      <div className="flex gap-2 items-center mb-4">
        <label className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Item:</label>
        <Typeahead
          options={items.map((i: any) => ({ value: String(i.id), label: `${i.code} — ${i.name}` }))}
          value={itemId !== '' ? String(itemId) : ''}
          onChange={v => { if (v) { setItemId(Number(v)); setForm({}) } }}
          placeholder="Select…" className="w-72"
        />
      </div>
      {itemId !== '' && (
        <div className="cyber-panel p-4 max-w-lg">
          <p className="text-xs mb-3" style={{ color: 'var(--c-text-sub)' }}>
            Item-level settings override category / group / store / hospital. Leave blank to inherit.
          </p>
          <label className="inline-flex items-center gap-2 mb-3 text-sm" style={{ color: 'var(--c-text)' }}>
            <input type="checkbox" checked={form.planning_enabled ?? true}
              onChange={e => update('planning_enabled', e.target.checked)} />
            Planning Enabled
          </label>
          <div className="grid grid-cols-2 gap-3">
            <NumField label="Pack Size (order multiple)" field="pack_size"
              form={form} update={update} min={1} step="1"
              hint="Indent rounded up to nearest multiple" />
            <NumField label="Lead Time (Days)" field="lead_time_days"
              form={form} update={update} min={0} step="1"
              hint="Overrides supplier lead time" />
            <NumField label="Indent Duration Days" field="indent_duration_days"
              form={form} update={update} min={1} step="1" />
            <NumField label="Safety Stock (Days)" field="safety_stock_days"
              form={form} update={update} min={0} hint="Days of demand as buffer" />
            <NumField label="Reorder Level" field="reorder_level" form={form} update={update} />
            <NumField label="Min Stock"     field="min_stock"     form={form} update={update} />
            <NumField label="Max Stock"     field="max_stock"     form={form} update={update} />
          </div>
          <SaveRow onSave={() => save.mutate()} isPending={save.isPending} />
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────
// Category Settings
// ─────────────────────────────────────────────
function CategorySettingsPanel() {
  const qc = useQueryClient()
  const [catId, setCatId] = useState<number | ''>('')
  const [form, setForm] = useState<any>({})

  const { data: categories = [] } = useQuery({ queryKey: ['itemCategories'], queryFn: getItemCategories })
  const { data: settings } = useQuery({
    queryKey: ['categorySettings', catId],
    queryFn: () => getCategorySettings(catId as number),
    enabled: catId !== '',
  })

  useEffect(() => { if (settings !== undefined) setForm(settings) }, [settings])

  const save = useMutation({
    mutationFn: () => upsertCategorySettings(catId as number, form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['categorySettings', catId] }),
  })

  function update(k: string, v: any) { setForm((f: any) => ({ ...f, [k]: v })) }

  return (
    <div>
      <div className="flex gap-2 items-center mb-4">
        <label className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Category:</label>
        <Typeahead
          options={categories.map((c: any) => ({ value: String(c.id), label: c.name }))}
          value={catId !== '' ? String(catId) : ''}
          onChange={v => { if (v) { setCatId(Number(v)); setForm({}) } }}
          placeholder="Select…" className="w-60"
        />
      </div>
      {catId !== '' && (
        <div className="cyber-panel p-4 max-w-lg">
          <p className="text-xs mb-3" style={{ color: 'var(--c-text-sub)' }}>
            Category settings apply to all items in this category, overriding group / store / hospital defaults.
            Leave blank to inherit.
          </p>
          <StockFields form={form} update={update} />
          <SaveRow onSave={() => save.mutate()} isPending={save.isPending} />
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────
// Group Settings
// ─────────────────────────────────────────────
function GroupSettingsPanel() {
  const qc = useQueryClient()
  const [groupId, setGroupId] = useState<number | ''>('')
  const [form, setForm] = useState<any>({})

  const { data: groups = [] } = useQuery({ queryKey: ['itemGroups'], queryFn: getItemGroups })
  const { data: settings } = useQuery({
    queryKey: ['groupSettings', groupId],
    queryFn: () => getGroupSettings(groupId as number),
    enabled: groupId !== '',
  })

  useEffect(() => { if (settings !== undefined) setForm(settings) }, [settings])

  const save = useMutation({
    mutationFn: () => upsertGroupSettings(groupId as number, form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['groupSettings', groupId] }),
  })

  function update(k: string, v: any) { setForm((f: any) => ({ ...f, [k]: v })) }

  return (
    <div>
      <div className="flex gap-2 items-center mb-4">
        <label className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Group:</label>
        <Typeahead
          options={groups.map((g: any) => ({ value: String(g.id), label: g.name }))}
          value={groupId !== '' ? String(groupId) : ''}
          onChange={v => { if (v) { setGroupId(Number(v)); setForm({}) } }}
          placeholder="Select…" className="w-60"
        />
      </div>
      {groupId !== '' && (
        <div className="cyber-panel p-4 max-w-lg">
          <p className="text-xs mb-3" style={{ color: 'var(--c-text-sub)' }}>
            Group settings apply to all items in this group, overriding store / hospital defaults.
            Leave blank to inherit.
          </p>
          <StockFields form={form} update={update} />
          <SaveRow onSave={() => save.mutate()} isPending={save.isPending} />
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────
// Item × Store Settings
// ─────────────────────────────────────────────
function ItemStoreSettingsPanel() {
  const qc = useQueryClient()
  const [itemId, setItemId]   = useState<number | ''>('')
  const [storeId, setStoreId] = useState<number | ''>('')
  const [form, setForm] = useState<any>({})

  const { data: items  = [] } = useQuery({ queryKey: ['items'],  queryFn: () => getItems() })
  const { data: stores = [] } = useQuery({ queryKey: ['stores'], queryFn: () => getStores() })

  const enabled = itemId !== '' && storeId !== ''
  const { data: settings } = useQuery({
    queryKey: ['itemStoreSettings', itemId, storeId],
    queryFn: () => getItemStoreSettings(itemId as number, storeId as number),
    enabled,
  })

  useEffect(() => { if (settings !== undefined) setForm(settings) }, [settings])

  const save = useMutation({
    mutationFn: () => upsertItemStoreSettings(itemId as number, storeId as number, form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['itemStoreSettings', itemId, storeId] }),
  })

  function update(k: string, v: any) { setForm((f: any) => ({ ...f, [k]: v })) }

  return (
    <div>
      <p className="text-sm mb-4" style={{ color: 'var(--c-text-sub)' }}>
        Item × Store settings are the <strong style={{ color: 'var(--c-cyan)' }}>highest-priority</strong> overrides,
        applying only to one specific item at one specific store.
      </p>
      <div className="flex flex-wrap gap-4 items-center mb-4">
        <div className="flex gap-2 items-center">
          <label className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Item:</label>
          <Typeahead
            options={items.map((i: any) => ({ value: String(i.id), label: `${i.code} — ${i.name}` }))}
            value={itemId !== '' ? String(itemId) : ''}
            onChange={v => { if (v) { setItemId(Number(v)); setForm({}) } }}
            placeholder="Select…" className="w-72"
          />
        </div>
        <div className="flex gap-2 items-center">
          <label className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Store:</label>
          <Typeahead
            options={stores.map((s: any) => ({ value: String(s.id), label: `${s.code} — ${s.name}` }))}
            value={storeId !== '' ? String(storeId) : ''}
            onChange={v => { if (v) { setStoreId(Number(v)); setForm({}) } }}
            placeholder="Select…" className="w-60"
          />
        </div>
      </div>
      {enabled && (
        <div className="cyber-panel p-4 max-w-lg">
          <StockFields form={form} update={update} />
          <SaveRow onSave={() => save.mutate()} isPending={save.isPending} />
        </div>
      )}
    </div>
  )
}
