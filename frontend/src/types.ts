export type Project = {
  id: string
  name: string
  path: string
  meta?: Record<string, unknown> | null
  created_at: string
}

export type ScanStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED'

export type ScanSummary = {
  id: string
  project_id: string
  name?: string | null
  status: ScanStatus
  tools: string[]
  target: string
  chain?: string | null
  meta?: Record<string, unknown> | null
  logs?: string | null
  created_at: string
  started_at?: string | null
  finished_at?: string | null
}

export type Finding = {
  id: string
  scan_id: string
  tool: string
  title: string
  description: string
  severity: string
  category?: string | null
  file_path?: string | null
  line_number?: string | null
  function?: string | null
  tool_version?: string | null
  input_seed?: string | null
  coverage?: Record<string, unknown> | null
  assertions?: Record<string, unknown> | null
  raw?: Record<string, unknown> | null
  created_at: string
}

export type ToolExecutionStatus = 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'RETRYING'

export type ToolExecution = {
  id: string
  scan_id: string
  tool: string
  status: ToolExecutionStatus
  attempt: number
  started_at?: string | null
  finished_at?: string | null
  duration_seconds?: number | null
  command?: string[] | null
  exit_code?: number | null
  stdout_path?: string | null
  stderr_path?: string | null
  environment?: Record<string, string> | null
  artifacts_path?: string | null
  error?: string | null
  parsing_error?: string | null
  failure_reason?: string | null
  findings_count: number
  tool_version?: string | null
  input_seed?: string | null
  coverage?: Record<string, unknown> | null
  assertions?: Record<string, unknown> | null
}

export type ScanDetail = ScanSummary & {
  findings: Finding[]
  tool_executions: ToolExecution[]
}

export type ToolInfo = {
  name: string
  kind: string
  docker_image: string
}

export type ProjectCreate = {
  name: string
  path: string
  meta?: Record<string, unknown> | null
}

export type ScanRequest = {
  project_id?: string | null
  project_name?: string | null
  project_path?: string | null
  target?: string | null
  tools?: string[]
  scan_name?: string | null
  log_file?: string | null
  chain?: string | null
  meta?: Record<string, unknown> | null
}
