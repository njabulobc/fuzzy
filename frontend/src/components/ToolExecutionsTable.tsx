import React from 'react'
import type { ToolExecution } from '../types'

type Props = {
  executions: ToolExecution[]
}

const statusColor = (status: string) => {
  switch (status) {
    case 'SUCCEEDED':
      return 'bg-emerald-100 text-emerald-800'
    case 'FAILED':
      return 'bg-rose-100 text-rose-800'
    case 'RUNNING':
      return 'bg-sky-100 text-sky-800'
    case 'RETRYING':
      return 'bg-amber-100 text-amber-800'
    default:
      return 'bg-slate-100 text-slate-800'
  }
}

export const ToolExecutionsTable: React.FC<Props> = ({ executions }) => {
  if (!executions.length) {
    return <p className="text-sm text-slate-500">No tool executions recorded yet.</p>
  }

  return (
    <div className="mt-4 max-h-72 overflow-auto rounded-lg border border-slate-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">Tool</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Attempt</th>
            <th className="px-3 py-2">Exit</th>
            <th className="px-3 py-2">Findings</th>
            <th className="px-3 py-2">Duration (s)</th>
            <th className="px-3 py-2">Reason</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {executions.map((e) => (
            <tr key={e.id} className="hover:bg-slate-50">
              <td className="px-3 py-2 text-xs font-semibold uppercase text-slate-700">{e.tool}</td>
              <td className="px-3 py-2">
                <span className={`fuzz-badge ${statusColor(e.status)}`}>{e.status}</span>
              </td>
              <td className="px-3 py-2 text-xs text-slate-600">{e.attempt}</td>
              <td className="px-3 py-2 text-xs text-slate-600">
                {e.exit_code !== null && e.exit_code !== undefined ? e.exit_code : '–'}
              </td>
              <td className="px-3 py-2 text-xs text-slate-600">{e.findings_count}</td>
              <td className="px-3 py-2 text-xs text-slate-600">
                {typeof e.duration_seconds === 'number' ? e.duration_seconds.toFixed(2) : '–'}
              </td>
              <td className="px-3 py-2 text-xs text-slate-600">
                {e.failure_reason ?? (e.error ? e.error.slice(0, 120) : '–')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
