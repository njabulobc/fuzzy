import React, { useMemo, useState } from 'react'
import type { Finding } from '../types'

type Props = {
  findings: Finding[]
}

const severityColor = (sev: string) => {
  const s = sev.toUpperCase()
  if (s === 'CRITICAL') return 'bg-rose-100 text-rose-800'
  if (s === 'HIGH') return 'bg-orange-100 text-orange-800'
  if (s === 'MEDIUM') return 'bg-amber-100 text-amber-800'
  if (s === 'LOW') return 'bg-emerald-100 text-emerald-800'
  return 'bg-slate-100 text-slate-800'
}

export const FindingsTable: React.FC<Props> = ({ findings }) => {
  const [severityFilter, setSeverityFilter] = useState<string>('ALL')
  const [toolFilter, setToolFilter] = useState<string>('ALL')
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    return findings.filter((f) => {
      if (severityFilter !== 'ALL' && f.severity.toUpperCase() !== severityFilter) return false
      if (toolFilter !== 'ALL' && f.tool.toLowerCase() !== toolFilter.toLowerCase()) return false
      if (search.trim()) {
        const haystack = `${f.title} ${f.description ?? ''} ${f.file_path ?? ''}`.toLowerCase()
        if (!haystack.includes(search.toLowerCase())) return false
      }
      return true
    })
  }, [findings, severityFilter, toolFilter, search])

  const severities = Array.from(new Set(findings.map((f) => f.severity.toUpperCase()))).sort()
  const tools = Array.from(new Set(findings.map((f) => f.tool.toLowerCase()))).sort()

  if (!findings.length) {
    return <p className="text-sm text-slate-500">No findings recorded for this scan.</p>
  }

  return (
    <div className="mt-4 space-y-3">
      <div className="flex flex-wrap gap-3">
        <select
          className="fuzz-input"
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
        >
          <option value="ALL">All severities</option>
          {severities.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select className="fuzz-input" value={toolFilter} onChange={(e) => setToolFilter(e.target.value)}>
          <option value="ALL">All tools</option>
          {tools.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          className="fuzz-input flex-1 min-w-[10rem]"
          placeholder="Search title, description, file..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="max-h-96 overflow-auto rounded-lg border border-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Severity</th>
              <th className="px-3 py-2">Tool</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">Location</th>
              <th className="px-3 py-2">Category</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.map((f) => (
              <tr key={f.id} className="hover:bg-slate-50">
                <td className="px-3 py-2">
                  <span className={`fuzz-badge ${severityColor(f.severity)}`}>{f.severity.toUpperCase()}</span>
                </td>
                <td className="px-3 py-2 text-xs font-semibold uppercase text-slate-600">{f.tool}</td>
                <td className="px-3 py-2">
                  <div className="font-semibold text-slate-900">{f.title}</div>
                  {f.description && (
                    <div className="mt-0.5 line-clamp-2 text-xs text-slate-500">{f.description}</div>
                  )}
                </td>
                <td className="px-3 py-2 text-xs text-slate-600">
                  {f.file_path ? (
                    <>
                      <code>{f.file_path}</code>
                      {f.line_number && <>:{f.line_number}</>}
                    </>
                  ) : (
                    <span className="text-slate-400">–</span>
                  )}
                </td>
                <td className="px-3 py-2 text-xs text-slate-600">{f.category ?? '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
