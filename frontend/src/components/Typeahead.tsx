import { useState, useRef, useEffect } from 'react'
import { X } from 'lucide-react'

export interface TypeaheadOption {
  value: string
  label: string
}

interface Props {
  options: TypeaheadOption[]
  value: string
  onChange: (v: string) => void
  placeholder?: string
  className?: string
  disabled?: boolean
  /** Server-backed mode. Called with the typed text, debounced.
   *
   *  When supplied, `options` are treated as ALREADY matching the query and are
   *  not filtered again locally — the backend did the matching, so results are
   *  not limited to whatever happened to be preloaded. */
  onQueryChange?: (q: string) => void
  /** Show a searching indicator (server-backed mode). */
  loading?: boolean
}

const DEBOUNCE_MS = 250

export default function Typeahead({
  options,
  value,
  onChange,
  placeholder = 'Search…',
  className = '',
  disabled = false,
  onQueryChange,
  loading = false,
}: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const remote = typeof onQueryChange === 'function'
  // In remote mode the current `options` reflect the latest search, which may
  // not contain the selected item any more — remember its label so the closed
  // control keeps showing the selection instead of falling back to the
  // placeholder.
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null)

  // Debounce the lift to the parent so typing does not fire a request per key.
  useEffect(() => {
    if (!remote || !open) return
    const t = setTimeout(() => onQueryChange!(query), DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [query, remote, open, onQueryChange])

  const selected = options.find(o => o.value === value)
  const displayLabel = selected?.label ?? (value ? selectedLabel : null)
  const filtered = remote
    ? options
    : query
      ? options.filter(o => o.label.toLowerCase().includes(query.toLowerCase()))
      : options
  // Cap the unfiltered list to avoid thousands of DOM nodes; when a query is typed show all matches
  const CAP = 200
  const showCap = !remote && !query
  const visible = showCap && filtered.length > CAP ? filtered.slice(0, CAP) : filtered
  const hasMore = showCap && filtered.length > CAP

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setQuery('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  function handleOpen() {
    if (disabled) return
    setOpen(true)
    setQuery('')
  }

  function handleSelect(val: string) {
    setSelectedLabel(options.find(o => o.value === val)?.label ?? null)
    onChange(val)
    setOpen(false)
    setQuery('')
  }

  function handleClear(e: React.MouseEvent) {
    e.stopPropagation()
    onChange('')
    setSelectedLabel(null)
    setOpen(false)
    setQuery('')
  }

  return (
    <div ref={ref} className={`relative ${className}`}>
      <div
        onClick={handleOpen}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.25rem',
          padding: '0.35rem 0.6rem',
          borderRadius: '0.375rem',
          background: 'var(--c-typeahead-bg, var(--c-card))',
          border: open
            ? '1px solid rgba(var(--c-accent-rgb), 0.55)'
            : '1px solid rgba(var(--c-accent-rgb), 0.22)',
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.5 : 1,
          transition: 'border-color 0.15s',
          boxShadow: open ? `0 0 0 2px rgba(var(--c-accent-rgb), 0.1)` : 'none',
          minHeight: '2rem',
        }}
      >
        {open ? (
          <input
            autoFocus
            style={{
              flex: 1,
              outline: 'none',
              fontSize: '0.75rem',
              background: 'transparent',
              minWidth: 0,
              color: 'var(--c-text)',
            }}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder={placeholder}
          />
        ) : (
          <span
            style={{
              flex: 1,
              fontSize: '0.75rem',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              color: displayLabel ? 'var(--c-text)' : 'var(--c-text-sub)',
            }}
          >
            {displayLabel ?? placeholder}
          </span>
        )}
        {value && !disabled && (
          <button
            type="button"
            onClick={handleClear}
            style={{ color: 'var(--c-text-sub)', flexShrink: 0, marginLeft: '0.25rem', lineHeight: 1 }}
          >
            <X size={11} />
          </button>
        )}
      </div>
      {open && (
        <div
          style={{
            position: 'absolute',
            zIndex: 50,
            marginTop: '0.25rem',
            width: '100%',
            background: 'var(--c-dropdown-bg, var(--c-card))',
            border: '1px solid rgba(var(--c-accent-rgb), 0.22)',
            borderRadius: '0.375rem',
            boxShadow: 'var(--c-dropdown-shadow, 0 8px 32px rgba(0,0,0,0.7))',
            maxHeight: '13rem',
            overflowY: 'auto',
          }}
        >
          {filtered.length === 0 ? (
            <div style={{ padding: '0.5rem 0.75rem', fontSize: '0.75rem', color: 'var(--c-text-sub)' }}>
              {loading ? 'Searching…' : 'No results'}
            </div>
          ) : (
            <>
              {visible.map(o => (
                <div
                  key={o.value}
                  onClick={() => handleSelect(o.value)}
                  style={{
                    padding: '0.4rem 0.75rem',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    color: o.value === value ? 'var(--c-cyan)' : 'var(--c-text)',
                    background: o.value === value ? `rgba(var(--c-accent-rgb), 0.1)` : 'transparent',
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => { if (o.value !== value) (e.currentTarget as HTMLElement).style.background = `rgba(var(--c-accent-rgb), 0.05)` }}
                  onMouseLeave={e => { if (o.value !== value) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                >
                  {o.label}
                </div>
              ))}
              {hasMore && (
                <div style={{ padding: '0.4rem 0.75rem', fontSize: '0.7rem', color: 'var(--c-text-sub)', borderTop: `1px solid rgba(var(--c-accent-rgb), 0.1)` }}>
                  {filtered.length - 200} more — type to narrow results
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
