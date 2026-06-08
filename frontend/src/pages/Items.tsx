import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getItems, createItem, updateItem, deleteItem,
  getItemGroups, createItemGroup, deleteItemGroup,
  getItemCategories, createItemCategory, updateItemCategory,
  getSuppliers,
} from '../api/client'
import PageHeader from '../components/PageHeader'
import Typeahead from '../components/Typeahead'
import TruncText from '../components/TruncText'
import { Plus, Pencil, Trash2, Search } from 'lucide-react'

type Tab = 'items' | 'groups' | 'categories'

export default function Items() {
  const [tab, setTab] = useState<Tab>('items')
  return (
    <div>
      <PageHeader title="Items" />
      <div className="flex gap-4 mb-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
        {(['items', 'groups', 'categories'] as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={tab === t ? 'cyber-tab-active' : 'cyber-tab'}>
            {t === 'groups' ? 'Item Groups' : t === 'categories' ? 'Item Categories' : 'Items'}
          </button>
        ))}
      </div>
      {tab === 'items' && <ItemsTable />}
      {tab === 'groups' && <GroupsTable />}
      {tab === 'categories' && <CategoriesTable />}
    </div>
  )
}

function ItemsTable() {
  const qc = useQueryClient()
  const [modal, setModal] = useState<any>(null)
  const [form, setForm] = useState({ name: '', code: '', unit: '', group_id: 0, category_id: 0, preferred_supplier_id: 0 })
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [search, setSearch] = useState('')

  const { data: items = [], isLoading } = useQuery({ queryKey: ['items'], queryFn: () => getItems() })
  const { data: groups = [] } = useQuery({ queryKey: ['itemGroups'], queryFn: getItemGroups })
  const { data: cats = [] } = useQuery({ queryKey: ['itemCategories'], queryFn: () => getItemCategories() })
  const { data: suppliers = [] } = useQuery({ queryKey: ['suppliers'], queryFn: getSuppliers })

  const save = useMutation({
    mutationFn: () => {
      const payload = { ...form, preferred_supplier_id: form.preferred_supplier_id || null }
      return modal === 'create' ? createItem(payload) : updateItem(modal.id, payload)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['items'] }); setModal(null) },
  })
  const remove = useMutation({
    mutationFn: (id: number) => deleteItem(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['items'] }); setDeleteId(null) },
  })

  function openCreate() {
    setForm({ name: '', code: '', unit: '', group_id: groups[0]?.id ?? 0, category_id: cats[0]?.id ?? 0, preferred_supplier_id: 0 })
    setModal('create')
  }

  const q = search.trim().toLowerCase()
  const visibleItems = q
    ? (items as any[]).filter(i =>
        i.name.toLowerCase().includes(q) || i.code.toLowerCase().includes(q))
    : items as any[]

  return (
    <>
      <div className="flex items-center gap-2 mb-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: 'var(--c-text-sub)' }} />
          <input
            className="form-input pl-7 w-full"
            placeholder="Search code or name…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <button onClick={openCreate} className="btn-primary flex items-center gap-1 ml-auto"><Plus size={14} /> Add Item</button>
      </div>
      {isLoading ? <p className="text-sm" style={{ color: 'var(--c-text-sub)' }}>Loading…</p> : (
        <div className="cyber-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="cyber-th">Code</th>
                <th className="cyber-th">Name</th><th className="cyber-th">Unit</th>
                <th className="cyber-th">Group</th><th className="cyber-th">Category</th>
                <th className="cyber-th">Preferred Supplier</th>
                <th className="cyber-th w-24">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleItems.map((item: any) => (
                <tr key={item.id} className="cyber-tr">
                  <td className="px-4 py-2 font-mono text-xs" style={{ color: 'var(--c-cyan)' }}><TruncText text={item.code} mono /></td>
                  <td className="px-4 py-2 font-medium"><TruncText text={item.name} style={{ color: 'var(--c-text)' }} /></td>
                  <td className="px-4 py-2" style={{ color: 'var(--c-text)' }}>{item.unit}</td>
                  <td className="px-4 py-2"><TruncText text={groups.find((g: any) => g.id === item.group_id)?.name ?? String(item.group_id)} style={{ color: 'var(--c-text)' }} /></td>
                  <td className="px-4 py-2"><TruncText text={cats.find((c: any) => c.id === item.category_id)?.name ?? String(item.category_id)} style={{ color: 'var(--c-text)' }} /></td>
                  <td className="px-4 py-2"><TruncText text={suppliers.find((s: any) => s.id === item.preferred_supplier_id)?.name ?? '—'} style={{ color: 'var(--c-text)' }} /></td>
                  <td className="px-4 py-2"><div className="flex gap-2">
                    <button onClick={() => { setForm({ name: item.name, code: item.code, unit: item.unit, group_id: item.group_id, category_id: item.category_id, preferred_supplier_id: item.preferred_supplier_id ?? 0 }); setModal(item) }} style={{ color: 'var(--c-text-sub)' }} className="hover:text-[var(--c-cyan)] transition-colors"><Pencil size={14} /></button>
                    <button onClick={() => setDeleteId(item.id)} style={{ color: 'var(--c-text-sub)' }} className="hover:text-[var(--c-red)] transition-colors"><Trash2 size={14} /></button>
                  </div></td>
                </tr>
              ))}
              {visibleItems.length === 0 && <tr><td colSpan={7} className="px-4 py-6 text-center text-sm" style={{ color: 'var(--c-text-sub)' }}>{q ? 'No matching items.' : 'No items.'}</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {modal !== null && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h2 className="text-base font-semibold mb-4" style={{ color: 'var(--c-cyan)' }}>{modal === 'create' ? 'Add Item' : 'Edit Item'}</h2>
            {(['name', 'code', 'unit'] as const).map(k => (
              <div key={k}>
                <label className="form-label capitalize">{k}</label>
                <input className="form-input" value={(form as any)[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))} />
              </div>
            ))}
            <label className="form-label mt-3">Group</label>
            <Typeahead
              options={groups.map((g: any) => ({ value: String(g.id), label: g.name }))}
              value={form.group_id ? String(form.group_id) : ''}
              onChange={v => setForm(f => ({ ...f, group_id: Number(v) }))}
              placeholder="Select group…"
            />
            <label className="form-label mt-3">Category</label>
            <Typeahead
              options={cats.map((c: any) => ({ value: String(c.id), label: c.name }))}
              value={form.category_id ? String(form.category_id) : ''}
              onChange={v => setForm(f => ({ ...f, category_id: Number(v) }))}
              placeholder="Select category…"
            />
            <label className="form-label mt-3">Preferred Supplier</label>
            <Typeahead
              options={[{ value: '0', label: '— None —' }, ...suppliers.map((s: any) => ({ value: String(s.id), label: s.name }))]}
              value={form.preferred_supplier_id ? String(form.preferred_supplier_id) : '0'}
              onChange={v => setForm(f => ({ ...f, preferred_supplier_id: Number(v) }))}
              placeholder="Select supplier…"
            />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setModal(null)} className="btn-secondary">Cancel</button>
              <button onClick={() => save.mutate()} disabled={save.isPending} className="btn-primary">{save.isPending ? 'Saving…' : 'Save'}</button>
            </div>
          </div>
        </div>
      )}
      {deleteId !== null && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <p className="text-sm mb-4" style={{ color: 'var(--c-text)' }}>Delete this item?</p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteId(null)} className="btn-secondary">Cancel</button>
              <button onClick={() => remove.mutate(deleteId)} className="btn-danger">Delete</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function GroupsTable() {
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [search, setSearch] = useState('')
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const { data: groups = [] } = useQuery({ queryKey: ['itemGroups'], queryFn: getItemGroups })
  const create = useMutation({
    mutationFn: () => createItemGroup({ name }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['itemGroups'] }); setName('') },
  })
  const remove = useMutation({
    mutationFn: (id: number) => deleteItemGroup(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['itemGroups'] }); setDeleteId(null) },
  })
  const q = search.trim().toLowerCase()
  const visibleGroups = q ? (groups as any[]).filter(g => g.name.toLowerCase().includes(q)) : groups as any[]
  return (
    <>
      <div className="flex gap-2 mb-3">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: 'var(--c-text-sub)' }} />
          <input className="form-input pl-7 w-48" placeholder="Search name…" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <input className="form-input flex-1" placeholder="New group name" value={name} onChange={e => setName(e.target.value)} />
        <button onClick={() => create.mutate()} className="btn-primary"><Plus size={14} /></button>
      </div>
      <div className="cyber-panel overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr><th className="cyber-th">Name</th><th className="cyber-th w-16">Del</th></tr></thead>
          <tbody>
            {visibleGroups.map((g: any) => (
              <tr key={g.id} className="cyber-tr">
                <td className="px-4 py-2 font-medium" style={{ color: 'var(--c-text)' }}>{g.name}</td>
                <td className="px-4 py-2"><button onClick={() => setDeleteId(g.id)} style={{ color: 'var(--c-text-sub)' }} className="hover:text-[var(--c-red)] transition-colors"><Trash2 size={14} /></button></td>
              </tr>
            ))}
            {visibleGroups.length === 0 && <tr><td colSpan={2} className="px-4 py-6 text-center text-sm" style={{ color: 'var(--c-text-sub)' }}>{q ? 'No matching groups.' : 'No groups.'}</td></tr>}
          </tbody>
        </table>
      </div>
      {deleteId !== null && (
        <div className="modal-backdrop"><div className="modal-box">
          <p className="text-sm mb-4" style={{ color: 'var(--c-text)' }}>Delete this group?</p>
          <div className="flex justify-end gap-2">
            <button onClick={() => setDeleteId(null)} className="btn-secondary">Cancel</button>
            <button onClick={() => remove.mutate(deleteId)} className="btn-danger">Delete</button>
          </div>
        </div></div>
      )}
    </>
  )
}

function CategoriesTable() {
  const qc = useQueryClient()
  const [modal, setModal] = useState<any>(null)
  const [form, setForm] = useState({ name: '', is_vital: false })
  const [search, setSearch] = useState('')
  const { data: cats = [] } = useQuery({ queryKey: ['itemCategories'], queryFn: () => getItemCategories() })
  const save = useMutation({
    mutationFn: () => modal === 'create' ? createItemCategory(form) : updateItemCategory(modal.id, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['itemCategories'] }); setModal(null) },
  })
  const q = search.trim().toLowerCase()
  const visibleCats = q ? (cats as any[]).filter(c => c.name.toLowerCase().includes(q)) : cats as any[]
  return (
    <>
      <div className="flex items-center gap-2 mb-3">
        <div className="relative flex-1 max-w-xs">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: 'var(--c-text-sub)' }} />
          <input className="form-input pl-7 w-full" placeholder="Search name…" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <button onClick={() => { setForm({ name: '', is_vital: false }); setModal('create') }} className="btn-primary flex items-center gap-1 ml-auto"><Plus size={14} /> Add Category</button>
      </div>
      <div className="cyber-panel overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr>
            <th className="cyber-th">Name</th><th className="cyber-th">Is Vital</th><th className="cyber-th w-16">Edit</th>
          </tr></thead>
          <tbody>
            {visibleCats.map((c: any) => (
              <tr key={c.id} className="cyber-tr">
                <td className="px-4 py-2 font-medium" style={{ color: 'var(--c-text)' }}>{c.name}</td>
                <td className="px-4 py-2">{c.is_vital ? <span className="badge-orange">Vital</span> : <span style={{ color: 'var(--c-text-sub)' }}>—</span>}</td>
                <td className="px-4 py-2"><button onClick={() => { setForm({ name: c.name, is_vital: c.is_vital }); setModal(c) }} style={{ color: 'var(--c-text-sub)' }} className="hover:text-[var(--c-cyan)] transition-colors"><Pencil size={14} /></button></td>
              </tr>
            ))}
            {visibleCats.length === 0 && <tr><td colSpan={3} className="px-4 py-6 text-center text-sm" style={{ color: 'var(--c-text-sub)' }}>{q ? 'No matching categories.' : 'No categories.'}</td></tr>}
          </tbody>
        </table>
      </div>
      {modal !== null && (
        <div className="modal-backdrop"><div className="modal-box">
          <h2 className="text-base font-semibold mb-4" style={{ color: 'var(--c-cyan)' }}>{modal === 'create' ? 'Add Category' : 'Edit Category'}</h2>
          <label className="form-label">Name</label>
          <input className="form-input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          <label className="flex items-center gap-2 mt-3 text-sm" style={{ color: 'var(--c-text)' }}>
            <input type="checkbox" checked={form.is_vital} onChange={e => setForm(f => ({ ...f, is_vital: e.target.checked }))} />
            Is Vital (suggests VED = V)
          </label>
          <div className="flex justify-end gap-2 mt-4">
            <button onClick={() => setModal(null)} className="btn-secondary">Cancel</button>
            <button onClick={() => save.mutate()} disabled={save.isPending} className="btn-primary">{save.isPending ? 'Saving…' : 'Save'}</button>
          </div>
        </div></div>
      )}
    </>
  )
}
