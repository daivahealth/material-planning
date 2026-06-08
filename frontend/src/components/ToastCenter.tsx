import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, X } from 'lucide-react'

type ToastKind = 'success' | 'error'

type ToastInput = {
  kind: ToastKind
  message: string
  durationMs?: number
}

type ToastRecord = ToastInput & {
  id: number
}

type ToastListener = (toast: ToastRecord) => void

const listeners = new Set<ToastListener>()
let nextToastId = 1
let lastToastKey = ''
let lastToastAt = 0

export function showToast(toast: ToastInput) {
  const message = toast.message.trim()
  if (!message) {
    return
  }

  const dedupeKey = `${toast.kind}:${message}`
  const now = Date.now()
  if (dedupeKey === lastToastKey && now - lastToastAt < 1200) {
    return
  }

  lastToastKey = dedupeKey
  lastToastAt = now

  const record: ToastRecord = {
    id: nextToastId++,
    durationMs: toast.durationMs ?? (toast.kind === 'error' ? 5500 : 3200),
    ...toast,
    message,
  }

  listeners.forEach(listener => listener(record))
}

function subscribe(listener: ToastListener) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export default function ToastCenter() {
  const [toasts, setToasts] = useState<ToastRecord[]>([])

  useEffect(() => subscribe(toast => {
    setToasts(current => [...current, toast])
    window.setTimeout(() => {
      setToasts(current => current.filter(entry => entry.id !== toast.id))
    }, toast.durationMs)
  }), [])

  return (
    <div className="toast-stack" aria-live="polite" aria-atomic="true">
      {toasts.map(toast => (
        <div key={toast.id} className={`toast-item toast-${toast.kind}`} role="status">
          <div className="toast-icon">
            {toast.kind === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          </div>
          <p className="toast-message">{toast.message}</p>
          <button
            type="button"
            onClick={() => setToasts(current => current.filter(entry => entry.id !== toast.id))}
            className="toast-close"
            aria-label="Dismiss notification"
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}