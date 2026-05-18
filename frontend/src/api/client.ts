import axios from 'axios'

const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const api = axios.create({ baseURL: BASE })

// ---- Masters ----
export const getHospitals = () => api.get('/api/masters/hospitals').then(r => r.data)
export const createHospital = (d: any) => api.post('/api/masters/hospitals', d).then(r => r.data)
export const updateHospital = (id: number, d: any) => api.put(`/api/masters/hospitals/${id}`, d).then(r => r.data)
export const deleteHospital = (id: number) => api.delete(`/api/masters/hospitals/${id}`)

export const getStores = (hospital_id?: number) =>
  api.get('/api/masters/stores', { params: hospital_id ? { hospital_id } : {} }).then(r => r.data)
export const createStore = (d: any) => api.post('/api/masters/stores', d).then(r => r.data)
export const updateStore = (id: number, d: any) => api.put(`/api/masters/stores/${id}`, d).then(r => r.data)
export const deleteStore = (id: number) => api.delete(`/api/masters/stores/${id}`)

export const getItemGroups = () => api.get('/api/masters/item-groups').then(r => r.data)
export const createItemGroup = (d: any) => api.post('/api/masters/item-groups', d).then(r => r.data)
export const deleteItemGroup = (id: number) => api.delete(`/api/masters/item-groups/${id}`)

export const getItemCategories = () => api.get('/api/masters/item-categories').then(r => r.data)
export const createItemCategory = (d: any) => api.post('/api/masters/item-categories', d).then(r => r.data)
export const updateItemCategory = (id: number, d: any) => api.put(`/api/masters/item-categories/${id}`, d).then(r => r.data)

export const getSuppliers = () => api.get('/api/masters/suppliers').then(r => r.data)
export const createSupplier = (d: any) => api.post('/api/masters/suppliers', d).then(r => r.data)

export const getItems = (params?: any) => api.get('/api/masters/items', { params: { limit: 200, ...params } }).then(r => r.data)
export const createItem = (d: any) => api.post('/api/masters/items', d).then(r => r.data)
export const updateItem = (id: number, d: any) => api.put(`/api/masters/items/${id}`, d).then(r => r.data)
export const deleteItem = (id: number) => api.delete(`/api/masters/items/${id}`)

export const getItemSuppliers = (item_id: number) =>
  api.get(`/api/masters/item-suppliers/${item_id}`).then(r => r.data)
export const createItemSupplier = (d: any) => api.post('/api/masters/item-suppliers', d).then(r => r.data)

// ---- Settings ----
export const resolveSettings = (item_id: number, store_id: number) =>
  api.get('/api/settings/resolve', { params: { item_id, store_id } }).then(r => r.data)
export const getHospitalSettings = (id: number) => api.get(`/api/settings/hospital/${id}`).then(r => r.data)
export const upsertHospitalSettings = (id: number, d: any) => api.put(`/api/settings/hospital/${id}`, d).then(r => r.data)
export const getStoreSettings = (id: number) => api.get(`/api/settings/store/${id}`).then(r => r.data)
export const upsertStoreSettings = (id: number, d: any) => api.put(`/api/settings/store/${id}`, d).then(r => r.data)
export const getItemSettings = (id: number) => api.get(`/api/settings/item/${id}`).then(r => r.data)
export const upsertItemSettings = (id: number, d: any) => api.put(`/api/settings/item/${id}`, d).then(r => r.data)

// ---- Imports ----
export const importConsumption = (file: File) => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/api/imports/consumption', fd).then(r => r.data)
}
export const importClosingStock = (file: File) => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/api/imports/closing-stock', fd).then(r => r.data)
}
export const importSurge = (file: File) => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/api/imports/surge', fd).then(r => r.data)
}
export const importOpenIndent = (file: File) => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/api/imports/open-indents', fd).then(r => r.data)
}
export const importItemGroups = (file: File) => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/api/imports/item-groups', fd).then(r => r.data)
}
export const importItemCategories = (file: File) => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/api/imports/item-categories', fd).then(r => r.data)
}
export const importItems = (file: File) => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/api/imports/items', fd).then(r => r.data)
}

// ---- Indents ----
export const generateIndent = (d: any) => api.post('/api/indents/generate', d).then(r => r.data)
export const generateBatch = (d: { store_id: number; as_of?: string; triggered_by?: string }) =>
  api.post('/api/indents/generate-batch', d).then(r => r.data)
export const getIndents = (params?: any) => api.get('/api/indents/', { params }).then(r => r.data)
export const exportIndents = (params?: any) => {
  const filtered: Record<string, string> = {}
  if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') filtered[k] = String(v) })
  const q = new URLSearchParams(filtered).toString()
  return `${BASE}/api/indents/export${q ? '?' + q : ''}`
}
export const clearIndents = (params?: { store_id?: number; item_id?: number }) =>
  api.delete('/api/indents/clear', { params }).then(r => r.data)
export const clearSurges = (params?: { store_id?: number; item_id?: number }) =>
  api.delete('/api/indents/surges/clear', { params }).then(r => r.data)
export const clearConsumption = (params?: { store_id?: number; item_id?: number }) =>
  api.delete('/api/imports/consumption', { params }).then(r => r.data)
export const clearClosingStock = (params?: { store_id?: number; item_id?: number }) =>
  api.delete('/api/imports/closing-stock', { params }).then(r => r.data)
export const clearOpenIndents = (params?: { store_id?: number; item_id?: number }) =>
  api.delete('/api/imports/open-indents', { params }).then(r => r.data)

// ---- Surges ----
export const createSurge = (d: any) => api.post('/api/indents/surges', d).then(r => r.data)
export const getSurges = (item_id?: number, store_id?: number, limit?: number) =>
  api.get('/api/indents/surges', { params: { item_id, store_id, ...(limit ? { limit } : {}) } }).then(r => r.data)

// ---- Classification ----
export const runFSN = (hospital_id: number) =>
  api.post('/api/classification/fsn/run', null, { params: { hospital_id } }).then(r => r.data)
export const getFSN = (params?: { hospital_id?: number; classification?: string; limit?: number; offset?: number }) =>
  api.get('/api/classification/fsn', { params }).then(r => r.data)
export const runVED = () => api.post('/api/classification/ved/run').then(r => r.data)
export const getVED = () => api.get('/api/classification/ved').then(r => r.data)
export const setVEDOverride = (item_id: number, d: { ved_class: string; reason: string }) =>
  api.put('/api/classification/ved/override', { item_id, ...d }).then(r => r.data)

// ---- Scheduler ----
export const getSchedulerStatus = () => api.get('/api/scheduler/status').then(r => r.data)
export const runJobNow = (job_id: string) => api.post(`/api/scheduler/run-now/${encodeURIComponent(job_id)}`).then(r => r.data)
export const runAllJobsNow = () => api.post('/api/scheduler/run-all').then(r => r.data)
