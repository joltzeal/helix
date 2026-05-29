import { invoke } from "@tauri-apps/api/core"

let apiBasePromise: Promise<string> | null = null

async function getApiBase() {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL
  }

  apiBasePromise ??= invoke<string>("api_endpoint").catch(() => "http://127.0.0.1:8765")
  return apiBasePromise
}

async function getWsBase() {
  return (await getApiBase()).replace(/^http/, "ws")
}

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

export interface PluginModule {
  key: string
  name: string
  version: string
  description: string
  entry: string
  status: string
  error: string
}

export interface BrowserHealthResponse {
  vendor: string
  ok: boolean
}

export interface ApiHealthResponse {
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
  const isFormData = init?.body instanceof FormData
  let response: Response

  try {
    response = await fetch(`${await getApiBase()}${path}`, {
      ...init,
      headers: isFormData
        ? init?.headers
        : {
            "Content-Type": "application/json",
            ...init?.headers,
          },
    })
  } catch (caught) {
    throw new Error(`无法连接后端服务：${getNetworkErrorMessage(caught)}`)
  }

  if (!response.ok) {
    const text = await response.text()
    throw new Error(parseErrorMessage(text) || `请求失败：${response.status}`)
  }

  return response.json() as Promise<T>
}

function getNetworkErrorMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

function parseErrorMessage(text: string) {
  if (!text) {
    return ""
  }

  try {
    const parsed = JSON.parse(text) as unknown
    if (typeof parsed === "object" && parsed !== null && "detail" in parsed) {
      const detail = (parsed as { detail: unknown }).detail
      if (typeof detail === "string") {
        return detail
      }
    }
  } catch {
    return text
  }

  return text
}

export const api = {
  checkApiHealth: () => apiFetch<ApiHealthResponse>("/health"),
  checkBrowserHealth: (vendor = "bit_browser") =>
    apiFetch<BrowserHealthResponse>(`/api/browsers/health/${vendor}`, {
      method: "POST",
    }),
  listTasks: () => apiFetch<TaskModule[]>("/api/tasks"),
  listPluginModules: () => apiFetch<PluginModule[]>("/api/task-modules"),
  reloadPluginModules: () =>
    apiFetch<PluginModule[]>("/api/task-modules/reload", {
      method: "POST",
    }),
  reloadPluginModule: (key: string) =>
    apiFetch<PluginModule>(`/api/task-modules/${key}/reload`, {
      method: "POST",
    }),
  deletePluginModule: (key: string) =>
    apiFetch<PluginModule[]>(`/api/task-modules/${key}`, {
      method: "DELETE",
    }),
  uploadPluginModule: (file: File) => {
    const body = new FormData()
    body.append("file", file)
    return apiFetch<PluginModule>("/api/task-modules/upload", {
      method: "POST",
      body,
    })
  },
  getTaskConfiguration: (taskKey: string) =>
    apiFetch<TaskConfigurationResponse>(`/api/tasks/configurations/${taskKey}`),
  saveTaskConfiguration: (taskKey: string, config: Record<string, unknown>) =>
    apiFetch<TaskConfigurationResponse>(`/api/tasks/configurations/${taskKey}`, {
      method: "PUT",
      body: JSON.stringify({ config }),
    }),
  listRuns: () => apiFetch<TaskRun[]>("/api/tasks/runs"),
  listRunLogs: (runId: string) => apiFetch<TaskRunLog[]>(`/api/tasks/runs/${runId}/logs`),
  runsWsUrl: async () => `${await getWsBase()}/api/tasks/runs/ws`,
  runLogsWsUrl: async (runId: string) => `${await getWsBase()}/api/tasks/runs/${runId}/logs/ws`,
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
