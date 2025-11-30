import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  createProject,
  getScan,
  listProjects,
  listScans,
  listTools,
  startScan,
  API_BASE_URL
} from './api'
import type {
  Project,
  ProjectCreate,
  ScanDetail,
  ScanSummary,
  ScanRequest,
  ToolInfo,
  ScanStatus
} from './types'
import { FindingsTable } from './components/FindingsTable'
import { ToolExecutionsTable } from './components/ToolExecutionsTable'
import { Toast, ToastStack } from './components/Toast'
import { initMonitoring, isMonitoringEnabled, logEvent, shutdownMonitoring } from './statsigClient'

type ProjectForm = {
  name: string
  path: string
}

type ScanForm = {
  project_id: string
  target: string
  tools: string[]
  scan_name: string
}

const DEFAULT_PROJECT_FORM: ProjectForm = {
  name: '',
  path: ''
}

const DEFAULT_SCAN_FORM: ScanForm = {
  project_id: '',
  target: 'contracts',
  tools: ['slither', 'echidna', 'foundry'],
  scan_name: ''
}

const STORAGE_KEYS = {
  projectForm: 'fuzz_projectForm',
  scanForm: 'fuzz_scanForm',
  selectedScanId: 'fuzz_selectedScanId',
  statsigUserId: 'fuzz_statsigUserId'
}

const statusColor: Record<ScanStatus, string> = {
  PENDING: 'bg-slate-100 text-slate-800',
  RUNNING: 'bg-sky-100 text-sky-800',
  SUCCESS: 'bg-emerald-100 text-emerald-800',
  FAILED: 'bg-rose-100 text-rose-800'
}

const App: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([])
  const [scans, setScans] = useState<ScanSummary[]>([])
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [selectedScanId, setSelectedScanId] = useState<string | null>(
    () => window.localStorage.getItem(STORAGE_KEYS.selectedScanId) || null
  )
  const [scanDetail, setScanDetail] = useState<ScanDetail | null>(null)
  const [projectForm, setProjectForm] = useState<ProjectForm>(() => {
    const raw = window.localStorage.getItem(STORAGE_KEYS.projectForm)
    return raw ? JSON.parse(raw) : DEFAULT_PROJECT_FORM
  })
  const [scanForm, setScanForm] = useState<ScanForm>(() => {
    const raw = window.localStorage.getItem(STORAGE_KEYS.scanForm)
    return raw ? JSON.parse(raw) : DEFAULT_SCAN_FORM
  })
  const [loadingProjects, setLoadingProjects] = useState(false)
  const [loadingScans, setLoadingScans] = useState(false)
  const [creatingProject, setCreatingProject] = useState(false)
  const [startingScan, setStartingScan] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [statsigUserId] = useState<string>(() => {
    const existing = window.localStorage.getItem(STORAGE_KEYS.statsigUserId)
    if (existing) return existing

    const generated =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : Math.random().toString(36).slice(2)
    window.localStorage.setItem(STORAGE_KEYS.statsigUserId, generated)
    return generated
  })
  const lastScanStatuses = useRef<Record<string, ScanStatus>>({})

  // ---------- Toast helpers ----------

  const pushToast = useCallback((tone: Toast['tone'], message: string) => {
    setToasts((prev) => [...prev, { id: Math.random().toString(36).slice(2), tone, message }])
  }, [])

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  // ---------- Persistence ----------

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.projectForm, JSON.stringify(projectForm))
  }, [projectForm])

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.scanForm, JSON.stringify(scanForm))
  }, [scanForm])

  useEffect(() => {
    if (selectedScanId) {
      window.localStorage.setItem(STORAGE_KEYS.selectedScanId, selectedScanId)
    }
  }, [selectedScanId])

  useEffect(() => {
    if (!isMonitoringEnabled()) return

    let cancelled = false
    void (async () => {
      await initMonitoring({ userID: statsigUserId })
      if (!cancelled) {
        await logEvent('frontend_session_started', null, {
          api_base: API_BASE_URL
        })
      }
    })()

    return () => {
      cancelled = true
      shutdownMonitoring()
    }
  }, [statsigUserId])

  // ---------- Initial data ----------

  const refreshProjects = useCallback(async () => {
    setLoadingProjects(true)
    try {
      const data = await listProjects()
      setProjects(data)
    } catch (err) {
      console.error(err)
      pushToast('error', 'Failed to load projects from API')
    } finally {
      setLoadingProjects(false)
    }
  }, [pushToast])

  const refreshScans = useCallback(async () => {
    setLoadingScans(true)
    try {
      const data = await listScans()
      setScans(data)
    } catch (err) {
      console.error(err)
      pushToast('error', 'Failed to load scans from API')
    } finally {
      setLoadingScans(false)
    }
  }, [pushToast])

  const refreshTools = useCallback(async () => {
    try {
      const data = await listTools()
      setTools(data)
    } catch (err) {
      console.error(err)
      // tools are nice-to-have; we don't need a toast here
    }
  }, [])

  useEffect(() => {
    void refreshProjects()
    void refreshScans()
    void refreshTools()
  }, [refreshProjects, refreshScans, refreshTools])

  // ---------- Scan detail polling ----------

  useEffect(() => {
    if (!selectedScanId) {
      setScanDetail(null)
      return
    }

    let cancelled = false
    let interval: number | undefined

    const load = async () => {
      try {
        const detail = await getScan(selectedScanId)
        if (cancelled) return
        setScanDetail(detail)

        if (detail.status === 'PENDING' || detail.status === 'RUNNING') {
          if (interval === undefined) {
            interval = window.setInterval(load, 4000)
          }
        } else if (interval !== undefined) {
          window.clearInterval(interval)
          interval = undefined
        }
      } catch (err) {
        console.error(err)
        if (!cancelled) pushToast('error', 'Failed to fetch scan detail')
      }
    }

    void load()

    return () => {
      cancelled = true
      if (interval !== undefined) window.clearInterval(interval)
    }
  }, [selectedScanId, pushToast])

  useEffect(() => {
    if (!selectedScanId) return
    void logEvent('scan_selected', null, { scan_id: selectedScanId })
  }, [selectedScanId])

  // ---------- Derived ----------

  const selectedScan = useMemo(
    () => (selectedScanId ? scans.find((s) => s.id === selectedScanId) ?? null : null),
    [scans, selectedScanId]
  )

  const activeProject = useMemo(
    () => (scanDetail ? projects.find((p) => p.id === scanDetail.project_id) ?? null : null),
    [projects, scanDetail]
  )

  const selectedToolNames = useMemo(() => new Set(scanForm.tools), [scanForm.tools])

  useEffect(() => {
    if (!scanDetail) return
    const previous = lastScanStatuses.current[scanDetail.id]
    if (previous === scanDetail.status) return

    lastScanStatuses.current[scanDetail.id] = scanDetail.status
    const metadata = {
      scan_id: scanDetail.id,
      project_id: scanDetail.project_id,
      status: scanDetail.status,
      tools: scanDetail.tools.join(', ')
    }

    if (scanDetail.status === 'RUNNING') {
      void logEvent('scan_running', null, metadata)
    }

    if (scanDetail.status === 'SUCCESS' || scanDetail.status === 'FAILED') {
      void logEvent('scan_completed', scanDetail.status, metadata)
    }
  }, [scanDetail])

  // ---------- Event handlers ----------

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault()
    const payload: ProjectCreate = {
      name: projectForm.name.trim(),
      path: projectForm.path.trim() || '.'
    }
    if (!payload.name || !payload.path) {
      pushToast('error', 'Project name and path are required')
      return
    }

    setCreatingProject(true)
    try {
      const created = await createProject(payload)
      void logEvent('project_created_frontend', null, {
        project_id: created.id,
        name: created.name
      })
      pushToast('success', `Project '${created.name}' created`)
      setProjectForm(DEFAULT_PROJECT_FORM)
      await refreshProjects()
    } catch (err: any) {
      console.error(err)
      const detail = err?.response?.data?.detail
      void logEvent('project_create_failed', null, {
        error: typeof detail === 'string' ? detail : 'unknown',
        name: payload.name
      })
      pushToast('error', typeof detail === 'string' ? detail : 'Failed to create project')
    } finally {
      setCreatingProject(false)
    }
  }

  const handleStartScan = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!scanForm.project_id) {
      pushToast('error', 'Select a project before starting a scan')
      return
    }
    const payload: ScanRequest = {
      project_id: scanForm.project_id,
      target: scanForm.target || null,
      tools: scanForm.tools,
      scan_name: scanForm.scan_name || null
    }

    setStartingScan(true)
    try {
      const scan = await startScan(payload)
      void logEvent('scan_started', null, {
        scan_id: scan.id,
        project_id: payload.project_id,
        tools: payload.tools.join(', ')
      })
      pushToast('success', 'Scan started')
      await refreshScans()
      setSelectedScanId(scan.id)
    } catch (err) {
      console.error(err)
      void logEvent('scan_start_failed', null, {
        project_id: payload.project_id,
        tools: payload.tools.join(', ')
      })
      pushToast('error', 'Failed to start scan')
    } finally {
      setStartingScan(false)
    }
  }

  const handleToggleTool = (name: string) => {
    setScanForm((prev) => {
      const has = prev.tools.includes(name)
      const tools = has ? prev.tools.filter((t) => t !== name) : [...prev.tools, name]
      return { ...prev, tools }
    })
  }

  // ---------- Render ----------

  return (
    <div className="fuzz-app flex min-h-screen flex-col bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 text-slate-50">
      <ToastStack toasts={toasts} onDismiss={dismissToast} />

      <header className="border-b border-slate-800 bg-slate-950/80 px-6 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-slate-50">fuzz</h1>
            <p className="text-xs text-slate-400">
              Smart contract fuzzing &amp; static analysis – Slither, Echidna, Foundry via Docker
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-slate-400">API: {API_BASE_URL}</p>
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-6 md:flex-row">
        {/* Left column: projects & new scan */}
        <section className="w-full md:w-1/3">
          <div className="fuzz-card mb-4 p-4">
            <h2 className="mb-2 text-sm font-semibold text-slate-900">Projects</h2>
            <div className="mb-3 flex items-center justify-between text-xs text-slate-500">
              <span>{projects.length} projects</span>
              {loadingProjects && <span className="animate-pulse">Refreshing…</span>}
            </div>
            <div className="max-h-56 overflow-auto rounded border border-slate-100">
              {projects.length === 0 ? (
                <div className="p-3 text-xs text-slate-500">No projects yet. Create one below.</div>
              ) : (
                <ul className="divide-y divide-slate-100 text-sm">
                  {projects.map((p) => (
                    <li
                      key={p.id}
                      className="flex cursor-pointer flex-col px-3 py-2 hover:bg-slate-50"
                      onClick={() =>
                        setScanForm((prev) => ({
                          ...prev,
                          project_id: p.id
                        }))
                      }
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-900">{p.name}</span>
                        {scanForm.project_id === p.id && (
                          <span className="fuzz-badge bg-sky-100 text-sky-800">selected</span>
                        )}
                      </div>
                      <span className="truncate text-xs text-slate-500">{p.path}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="fuzz-card mb-4 p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-900">New project</h2>
            <form className="space-y-3" onSubmit={handleCreateProject}>
              <div className="space-y-1 text-xs">
                <label className="font-medium text-slate-700">Project name</label>
                <input
                  className="fuzz-input w-full"
                  value={projectForm.name}
                  onChange={(e) =>
                    setProjectForm((prev) => ({
                      ...prev,
                      name: e.target.value
                    }))
                  }
                  placeholder="ex: sample-audits"
                  required
                />
              </div>
              <div className="space-y-1 text-xs">
                <label className="font-medium text-slate-700">Path to contracts (host path)</label>
                <input
                  className="fuzz-input w-full"
                  value={projectForm.path}
                  onChange={(e) =>
                    setProjectForm((prev) => ({
                      ...prev,
                      path: e.target.value
                    }))
                  }
                  placeholder="C:\\Users\\you\\Desktop\\contracts"
                  required
                />
              </div>
              <button className="fuzz-button-primary w-full" disabled={creatingProject}>
                {creatingProject ? 'Creating…' : 'Create project'}
              </button>
            </form>
          </div>

          <div className="fuzz-card p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-900">Start scan</h2>
            <form className="space-y-3" onSubmit={handleStartScan}>
              <div className="space-y-1 text-xs">
                <label className="font-medium text-slate-700">Project</label>
                <select
                  className="fuzz-input w-full"
                  value={scanForm.project_id}
                  onChange={(e) =>
                    setScanForm((prev) => ({
                      ...prev,
                      project_id: e.target.value
                    }))
                  }
                  required
                >
                  <option value="">Select a project…</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1 text-xs">
                <label className="font-medium text-slate-700">Target (relative to project path)</label>
                <input
                  className="fuzz-input w-full"
                  value={scanForm.target}
                  onChange={(e) =>
                    setScanForm((prev) => ({
                      ...prev,
                      target: e.target.value
                    }))
                  }
                  placeholder="contracts/MyToken.sol or contracts/"
                  required
                />
              </div>
              <div className="space-y-1 text-xs">
                <label className="font-medium text-slate-700">Scan name (optional)</label>
                <input
                  className="fuzz-input w-full"
                  value={scanForm.scan_name}
                  onChange={(e) =>
                    setScanForm((prev) => ({
                      ...prev,
                      scan_name: e.target.value
                    }))
                  }
                  placeholder="ex: pre-deploy review"
                />
              </div>
              <div className="space-y-1 text-xs">
                <label className="font-medium text-slate-700">Tools</label>
                <div className="flex flex-wrap gap-2 text-xs">
                  {(tools.length ? tools.map((t) => t.name) : ['slither', 'echidna', 'foundry']).map((name) => {
                    const selected = selectedToolNames.has(name)
                    return (
                      <button
                        key={name}
                        type="button"
                        className={`rounded-full border px-2 py-1 ${
                          selected
                            ? 'border-sky-500 bg-sky-100 text-sky-800'
                            : 'border-slate-200 bg-slate-50 text-slate-600'
                        }`}
                        onClick={() => handleToggleTool(name)}
                      >
                        {name}
                      </button>
                    )
                  })}
                </div>
              </div>
              <button className="fuzz-button-primary w-full" disabled={startingScan}>
                {startingScan ? 'Starting…' : 'Start scan'}
              </button>
            </form>
          </div>
        </section>

        {/* Right column: scans & details */}
        <section className="w-full md:w-2/3">
          <div className="fuzz-card mb-4 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-900">Scans</h2>
              <button
                className="text-xs font-medium text-slate-500 hover:text-slate-800"
                onClick={() => refreshScans()}
              >
                {loadingScans ? 'Refreshing…' : 'Refresh'}
              </button>
            </div>
            <div className="max-h-48 overflow-auto rounded border border-slate-100">
              {scans.length === 0 ? (
                <div className="p-3 text-xs text-slate-500">
                  No scans yet. Start one from the form on the left.
                </div>
              ) : (
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2">Target</th>
                      <th className="px-3 py-2">Tools</th>
                      <th className="px-3 py-2">Created</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {scans.map((s) => (
                      <tr
                        key={s.id}
                        className={`cursor-pointer hover:bg-slate-50 ${
                          selectedScanId === s.id ? 'bg-slate-50/60' : ''
                        }`}
                        onClick={() => setSelectedScanId(s.id)}
                      >
                        <td className="px-3 py-2">
                          <span className={`fuzz-badge ${statusColor[s.status]}`}>{s.status}</span>
                        </td>
                        <td className="px-3 py-2 text-xs text-slate-700">
                          <div className="truncate font-medium text-slate-900">{s.target}</div>
                          {s.name && <div className="text-[11px] text-slate-500">{s.name}</div>}
                        </td>
                        <td className="px-3 py-2 text-xs text-slate-600">
                          {s.tools && s.tools.length ? s.tools.join(', ') : '–'}
                        </td>
                        <td className="px-3 py-2 text-xs text-slate-500">
                          {new Date(s.created_at).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          <div className="fuzz-card p-4">
            {!scanDetail ? (
              <p className="text-sm text-slate-500">Select a scan above to view details.</p>
            ) : (
              <>
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-semibold text-slate-900">
                      Scan detail – <span className="text-slate-700">{scanDetail.target}</span>
                    </h2>
                    <p className="text-xs text-slate-500">
                      Project:{' '}
                      {activeProject ? (
                        <>
                          {activeProject.name} <span className="text-slate-400">({activeProject.path})</span>
                        </>
                      ) : (
                        'Unknown'
                      )}
                    </p>
                  </div>
                  <div className="text-right text-xs text-slate-500">
                    <div>
                      Status:{' '}
                      <span className={`fuzz-badge ${statusColor[scanDetail.status]}`}>
                        {scanDetail.status}
                      </span>
                    </div>
                    <div>Tools: {scanDetail.tools.join(', ')}</div>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Tool executions
                    </h3>
                    <ToolExecutionsTable executions={scanDetail.tool_executions} />
                  </div>
                  <div>
                    <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Findings
                    </h3>
                    <FindingsTable findings={scanDetail.findings} />
                  </div>
                </div>

                {scanDetail.logs && (
                  <div className="mt-4">
                    <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Worker logs snapshot
                    </h3>
                    <pre className="max-h-40 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
                      {scanDetail.logs}
                    </pre>
                  </div>
                )}
              </>
            )}
          </div>
        </section>
      </main>
    </div>
  )
}

export default App
