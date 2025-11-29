import React from 'react'

export type ToastTone = 'info' | 'success' | 'error'

export type Toast = {
  id: string
  tone: ToastTone
  message: string
}

type Props = {
  toasts: Toast[]
  onDismiss: (id: string) => void
}

export const ToastStack: React.FC<Props> = ({ toasts, onDismiss }) => {
  if (!toasts.length) return null

  const toneClasses: Record<ToastTone, string> = {
    info: 'border-sky-400 bg-sky-50 text-sky-900',
    success: 'border-emerald-400 bg-emerald-50 text-emerald-900',
    error: 'border-rose-400 bg-rose-50 text-rose-900'
  }

  return (
    <div className="fixed right-4 top-4 z-50 flex max-w-md flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`flex items-start justify-between gap-3 rounded-lg border px-3 py-2 text-sm shadow-lg ${toneClasses[toast.tone]}`}
        >
          <span>{toast.message}</span>
          <button
            aria-label="Dismiss"
            className="text-xs font-semibold opacity-70 hover:opacity-100"
            onClick={() => onDismiss(toast.id)}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
