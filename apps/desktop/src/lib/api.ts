const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8765"
const WS_BASE = API_BASE.replace(/^http/, "ws")

export type TaskFieldType = "text" | "password" | "number" | "textarea" | "select" | "multi-select" | "checkbox"
export type LogLevel = "info" | "warn" | "error" | "debug" | "verbose"

export interface TaskConfigField {
  key: string
  label: string
  block: string
  field_type: TaskFieldType
  required: boolean
  description: string
  placeholder: string
  default: unknown
  options: string[]
}

export interface TaskResultBlock {
  key: string
  label: string
  source_key: string
  description: string
}

export interface TaskModule {
  key: string
  name: string
  description: string
  config_fields: TaskConfigField[]
  result_blocks: TaskResultBlock[]
}

export interface BrowserHealthResponse {
  vendor: string
  ok: boolean
}

export interface TaskRunItem {
  id: string
  item_index: number
  profile_id: string | null
  status: string
  debug_address: string | null
  websocket_url: string | null
  pid: number | null
  seq: number | null
  message: string
  error: string | null
  started_at: string | null
  finished_at: string | null
}

export interface TaskRunLog {
  id: string
  level: LogLevel
  message: string
  timestamp: string
  item_id: string | null
  seq: number | null
}

export interface TaskRun {
  id: string
  task_key: string
  task_name: string
  vendor: string
  status: string
  concurrency: number
  total: number
  completed: number
  failed: number
  config: Record<string, unknown>
  items: TaskRunItem[]
  logs: TaskRunLog[]
  result_json: Record<string, unknown>[]
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface CreateTaskRunPayload {
  task_key: string
  vendor: string
  concurrency: number
  config: Record<string, unknown>
}

export interface TaskConfigurationResponse {
  task_key: string
  config: Record<string, unknown>
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    ...init,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }

  return response.json() as Promise<T>
}

export const api = {
  checkBrowserHealth: (vendor = "bit_browser") =>
    apiFetch<BrowserHealthResponse>(`/api/browsers/health/${vendor}`, {
      method: "POST",
    }),
  listTasks: () => apiFetch<TaskModule[]>("/api/tasks"),
  getTaskConfiguration: (taskKey: string) =>
    apiFetch<TaskConfigurationResponse>(`/api/tasks/configurations/${taskKey}`),
  saveTaskConfiguration: (taskKey: string, config: Record<string, unknown>) =>
    apiFetch<TaskConfigurationResponse>(`/api/tasks/configurations/${taskKey}`, {
      method: "PUT",
      body: JSON.stringify({ config }),
    }),
  listRuns: () => apiFetch<TaskRun[]>("/api/tasks/runs"),
  listRunLogs: (runId: string) => apiFetch<TaskRunLog[]>(`/api/tasks/runs/${runId}/logs`),
  runsWsUrl: () => `${WS_BASE}/api/tasks/runs/ws`,
  runLogsWsUrl: (runId: string) => `${WS_BASE}/api/tasks/runs/${runId}/logs/ws`,
  createRun: (payload: CreateTaskRunPayload) =>
    apiFetch<TaskRun>("/api/tasks/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  stopRun: (runId: string) =>
    apiFetch<TaskRun>(`/api/tasks/runs/${runId}/stop`, {
      method: "POST",
    }),
  stopActiveRun: () =>
    apiFetch<TaskRun>("/api/tasks/runs/active/stop", {
      method: "POST",
    }),
}
