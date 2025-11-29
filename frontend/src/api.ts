import axios from 'axios'
import type {
  Project,
  ProjectCreate,
  ScanSummary,
  ScanDetail,
  ToolInfo,
  ScanRequest
} from './types'

const defaultApiBase = (() => {
  if (typeof window === 'undefined') return 'http://localhost:8000/api'
  const origin = window.location.origin || 'http://localhost:8000'
  return `${origin.replace(/\/$/, '')}/api`
})()

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? defaultApiBase

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000
})

export async function listProjects(): Promise<Project[]> {
  const res = await client.get<Project[]>('/projects')
  return res.data
}

export async function createProject(payload: ProjectCreate): Promise<Project> {
  const res = await client.post<Project>('/projects', payload)
  return res.data
}

export async function listScans(): Promise<ScanSummary[]> {
  const res = await client.get<ScanSummary[]>('/scans')
  return res.data
}

export async function getScan(scanId: string): Promise<ScanDetail> {
  const res = await client.get<ScanDetail>(`/scans/${encodeURIComponent(scanId)}`)
  return res.data
}

export async function startScan(payload: ScanRequest): Promise<ScanSummary> {
  const res = await client.post<ScanSummary>('/scans', payload)
  return res.data
}

export async function listTools(): Promise<ToolInfo[]> {
  const res = await client.get<ToolInfo[]>('/tools')
  return res.data
}
