import { useState, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { importConsumption, importClosingStock, importSurge, importOpenIndent, importItemGroups, importItemCategories, importItems } from '../api/client'
import PageHeader from '../components/PageHeader'
import { UploadCloud, CheckCircle, AlertCircle } from 'lucide-react'

type Result = { imported: number; errors: { row: number; message: string }[] } | null

function ImportSection({ title, description, onImport }: {
  title: string
  description: string
  onImport: (file: File) => Promise<any>
}) {
  const [result, setResult] = useState<Result>(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const { mutate, isPending, isError, error } = useMutation({
    mutationFn: onImport,
    onSuccess: (data) => setResult(data),
    onError: () => setResult(null),
  })

  function handle(file: File | null | undefined) {
    if (!file) return
    if (!file.name.endsWith('.csv')) { alert('Please upload a .csv file'); return }
    mutate(file)
  }

  return (
    <div className="cyber-panel p-5 mb-5">
      <h2 className="text-sm font-semibold mb-1" style={{ color: 'var(--c-cyan)' }}>{title}</h2>
      <p className="text-xs mb-3" style={{ color: 'var(--c-text-sub)' }}>{description}</p>

      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); handle(e.dataTransfer.files[0]) }}
        style={{
          border: dragging ? '2px dashed rgba(0,212,255,0.7)' : '2px dashed rgba(0,212,255,0.2)',
          background: dragging ? 'rgba(0,212,255,0.06)' : 'rgba(0,0,0,0.25)',
          borderRadius: '0.5rem',
          padding: '1.5rem',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          cursor: 'pointer',
          transition: 'all 0.2s',
        }}
      >
        <UploadCloud size={24} style={{ color: dragging ? 'var(--c-cyan)' : 'var(--c-text-sub)', marginBottom: '0.5rem' }} />
        <p className="text-sm" style={{ color: dragging ? 'var(--c-cyan)' : 'var(--c-text-sub)' }}>{isPending ? 'Importing…' : 'Drag & drop or click to upload CSV'}</p>
        <input ref={inputRef} type="file" accept=".csv" className="hidden" onChange={e => handle(e.target.files?.[0])} />
      </div>

      {isError && <p className="text-xs mt-2" style={{ color: 'var(--c-red)' }}>{(error as any)?.response?.data?.detail ?? 'Import failed'}</p>}

      {result && (
        <div className="mt-3">
          <div className="flex items-center gap-2 text-sm">
            <CheckCircle size={14} style={{ color: 'var(--c-green)' }} />
            <span className="font-medium" style={{ color: 'var(--c-green)' }}>{result.imported} rows imported</span>
            {result.errors.length > 0 && (
              <span className="ml-2 flex items-center gap-1" style={{ color: 'var(--c-orange)' }}>
                <AlertCircle size={13} /> {result.errors.length} errors
              </span>
            )}
          </div>
          {result.errors.length > 0 && (
            <div className="mt-2 max-h-40 overflow-y-auto rounded p-2" style={{ border: '1px solid rgba(255,158,0,0.3)', background: 'rgba(255,158,0,0.06)' }}>
              <table className="w-full text-xs">
                <thead><tr className="text-left" style={{ color: 'var(--c-orange)' }}><th className="pb-1">Row</th><th>Message</th></tr></thead>
                <tbody>
                  {result.errors.map((e, i) => (
                    <tr key={i} style={{ borderTop: '1px solid rgba(255,158,0,0.15)' }}>
                      <td className="py-0.5 pr-3" style={{ color: 'var(--c-text)' }}>{e.row}</td>
                      <td style={{ color: 'var(--c-text)' }}>{e.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function Imports() {
  return (
    <div>
      <PageHeader title="CSV Import">Import master data and transactional records from CSV files.</PageHeader>
      <div className="max-w-2xl">
        <p className="text-xs font-bold uppercase tracking-widest mb-3" style={{ color: 'var(--c-text-sub)' }}>Master Data</p>
        <ImportSection
          title="Item Groups"
          description="Columns: name"
          onImport={importItemGroups}
        />
        <ImportSection
          title="Item Categories"
          description="Columns: name, is_vital (optional — true/false, default false)"
          onImport={importItemCategories}
        />
        <ImportSection
          title="Items"
          description="Columns: code, name, unit, group_name (optional), category_name (optional)"
          onImport={importItems}
        />
        <p className="text-xs font-bold uppercase tracking-widest mb-3 mt-6" style={{ color: 'var(--c-text-sub)' }}>Transactional Data</p>
        <ImportSection
          title="Consumption Records"
          description="Columns: item_code, store_code, date (YYYY-MM-DD), quantity"
          onImport={importConsumption}
        />
        <ImportSection
          title="Closing Stock"
          description="Columns: item_code, store_code, date (YYYY-MM-DD), quantity"
          onImport={importClosingStock}
        />
        <ImportSection
          title="Surge Records"
          description="Columns: item_code, store_code, recorded_date, extra_qty, reason, season (optional — auto-detected if blank)"
          onImport={importSurge}
        />
        <ImportSection
          title="Open Indents (Pending Orders)"
          description="Columns: item_code, store_code, as_of_date (YYYY-MM-DD), quantity, reference (optional). These quantities are subtracted from the projected requirement to avoid double-ordering already-placed indents."
          onImport={importOpenIndent}
        />
      </div>
    </div>
  )
}
