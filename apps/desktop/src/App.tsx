import { createListCollection } from "@ark-ui/react"
import { getVersion } from "@tauri-apps/api/app"
import { isTauri } from "@tauri-apps/api/core"
import { useEffect, useMemo, useRef, useState } from "react"
import {
  ActivityIcon,
  ChevronDownIcon,
  DownloadIcon,
  PackageIcon,
  Settings2Icon,
  PlayIcon,
  RefreshCwIcon,
  ReceiptTextIcon,
  Rows3Icon,
  SquareIcon,
  Trash2Icon,
  UploadIcon,
  WorkflowIcon,
} from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldSet,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { Progress } from "@/components/ui/progress"
import {
  Select,
  SelectContent,
  SelectContext,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { AutoUpdateDialog } from "@/components/auto-update-dialog"
import { LogViewerTerminal } from "@/components/log-viewer"
import packageJson from "../package.json"
import {
  api,
  type PluginModule,
  type TaskConfigField,
  type TaskModule,
  type TaskResultBlock,
  type TaskRun,
  type TaskRunLog,
} from "@/lib/api"

const VENDOR = "bit_browser"
const PACKAGE_VERSION = packageJson.version
const WINDOW_ARRANGE_STORAGE_KEY = "helix.windowArrangeSettings"
const DEFAULT_WINDOW_ARRANGE_SETTINGS = {
  startX: 0,
  startY: 0,
  width: 500,
  height: 950,
  col: 3,
  spaceX: -200,
  spaceY: 0,
}

type Page = "launcher" | "records" | "modules"
type TaskResult = Record<string, unknown>
type WindowArrangeSettingKey = keyof typeof DEFAULT_WINDOW_ARRANGE_SETTINGS
type WindowArrangeSettings = Record<WindowArrangeSettingKey, number>
interface TaskResultGroup {
  runId: string
  taskName: string
  status: string
  createdAt: string
  results: TaskResult[]
}

function App() {
  const [page, setPage] = useState<Page>("launcher")
  const [tasks, setTasks] = useState<TaskModule[]>([])
  const [pluginModules, setPluginModules] = useState<PluginModule[]>([])
  const [runs, setRuns] = useState<TaskRun[]>([])
  const [logsByRunId, setLogsByRunId] = useState<Record<string, TaskRunLog[]>>({})
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [selectedTaskKey, setSelectedTaskKey] = useState("")
  const [concurrency, setConcurrency] = useState(1)
  const [config, setConfig] = useState<Record<string, unknown>>({})
  const [browserHealth, setBrowserHealth] = useState<"checking" | "online" | "offline">("checking")
  const [error, setError] = useState<string | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [isStopping, setIsStopping] = useState(false)
  const [isSavingConfig, setIsSavingConfig] = useState(false)
  const [isUploadingPlugin, setIsUploadingPlugin] = useState(false)
  const [isReloadingPlugins, setIsReloadingPlugins] = useState(false)
  const [isArrangeDialogOpen, setIsArrangeDialogOpen] = useState(false)
  const [isArrangingWindows, setIsArrangingWindows] = useState(false)
  const [windowArrangeSettings, setWindowArrangeSettings] = useState<WindowArrangeSettings>(() => loadWindowArrangeSettings())
  const [windowArrangeDraft, setWindowArrangeDraft] = useState<WindowArrangeSettings>(windowArrangeSettings)
  const [appVersion, setAppVersion] = useState(PACKAGE_VERSION)

  const selectedTask = useMemo(
    () => tasks.find((task) => task.key === selectedTaskKey) ?? tasks[0],
    [selectedTaskKey, tasks],
  )
  const activeLogs = activeRunId ? logsByRunId[activeRunId] ?? [] : []
  const runningRun = useMemo(
    () => runs.find((run) => isRunActive(run)) ?? null,
    [runs],
  )

  useEffect(() => {
    void loadInitialData()
  }, [])

  useEffect(() => {
    if (!isTauri()) {
      return
    }

    let disposed = false

    async function loadAppVersion() {
      try {
        const version = await getVersion()
        if (!disposed && version) {
          setAppVersion(version)
        }
      } catch (caught) {
        console.warn("Failed to load app version", caught)
      }
    }

    void loadAppVersion()

    return () => {
      disposed = true
    }
  }, [])

  useEffect(() => {
    let disposed = false
    let socket: WebSocket | null = null
    let retryTimer = 0
    let retryCount = 0

    const connect = () => {
      socket = new WebSocket(api.runsWsUrl())

      socket.onopen = () => {
        if (disposed) {
          socket?.close()
          return
        }
        retryCount = 0
        setError((current) => (isBackendConnectionMessage(current) ? null : current))
      }

      socket.onmessage = (event) => {
        if (disposed) {
          return
        }
        const run = JSON.parse(event.data) as TaskRun
        setRuns((current) => upsertRun(current, run))
        setLogsByRunId((current) => mergeRunLogs(current, run.id, run.logs))
        setActiveRunId((current) => current ?? run.id)
      }

      socket.onerror = () => {
        socket?.close()
      }

      socket.onclose = () => {
        if (disposed) {
          return
        }
        retryCount += 1
        setError(retryCount < 20 ? "程序正在启动，请稍候。" : "运行状态连接失败。")
        retryTimer = window.setTimeout(connect, Math.min(1000 + retryCount * 250, 5000))
      }
    }

    connect()

    return () => {
      disposed = true
      window.clearTimeout(retryTimer)
      if (socket) {
        closeWebSocket(socket)
      }
    }
  }, [])

  useEffect(() => {
    if (!activeRunId) {
      return
    }

    let disposed = false
    let socket: WebSocket | null = null
    let retryTimer = 0
    let retryCount = 0

    const connect = () => {
      socket = new WebSocket(api.runLogsWsUrl(activeRunId))

      socket.onopen = () => {
        if (disposed) {
          socket?.close()
          return
        }
        retryCount = 0
        setError((current) => (current === "日志连接失败。" ? null : current))
      }

      socket.onmessage = (event) => {
        if (disposed) {
          return
        }
        const log = JSON.parse(event.data) as TaskRunLog
        setLogsByRunId((current) => mergeRunLogs(current, activeRunId, [log]))
      }

      socket.onerror = () => {
        socket?.close()
      }

      socket.onclose = () => {
        if (disposed) {
          return
        }
        retryCount += 1
        if (retryCount >= 20) {
          setError("日志连接失败。")
        }
        retryTimer = window.setTimeout(connect, Math.min(1000 + retryCount * 250, 5000))
      }
    }

    connect()

    return () => {
      disposed = true
      window.clearTimeout(retryTimer)
      if (socket) {
        closeWebSocket(socket)
      }
    }
  }, [activeRunId])

  useEffect(() => {
    if (!selectedTask) {
      return
    }

    let disposed = false
    const defaults = defaultConfigForTask(selectedTask)

    async function loadTaskConfiguration() {
      try {
        const saved = await api.getTaskConfiguration(selectedTask.key)
        if (!disposed) {
          setConfig({ ...defaults, ...configForTask(selectedTask, saved.config) })
        }
      } catch (caught) {
        if (!disposed) {
          setConfig(defaults)
          setError(getErrorMessage(caught))
        }
      }
    }

    void loadTaskConfiguration()

    return () => {
      disposed = true
    }
  }, [selectedTask])

  async function loadInitialData() {
    const ready = await waitForApiReady()
    if (!ready) {
      setError("程序启动超时，请重启应用。")
      return
    }
    await Promise.all([refreshTasks(), refreshRuns(), refreshPluginModules(), checkBrowserHealth()])
  }

  async function refreshTasks() {
    try {
      const nextTasks = await api.listTasks()
      setTasks(nextTasks)
      if (nextTasks.length > 0 && !nextTasks.some((task) => task.key === selectedTaskKey)) {
        setSelectedTaskKey(nextTasks[0].key)
      }
    } catch (caught) {
      setError(getErrorMessage(caught))
    }
  }

  async function refreshRuns() {
    try {
      const nextRuns = await api.listRuns()
      setRuns(nextRuns)
      setLogsByRunId((current) =>
        nextRuns.reduce(
          (next, run) => mergeRunLogs(next, run.id, run.logs),
          current,
        ),
      )
      const latestRun = nextRuns[0]
      setActiveRunId((current) => current ?? latestRun?.id ?? null)
    } catch (caught) {
      setError(getErrorMessage(caught))
    }
  }

  async function refreshPluginModules() {
    try {
      const nextPluginModules = await api.listPluginModules()
      setPluginModules(nextPluginModules)
    } catch (caught) {
      setError(getErrorMessage(caught))
    }
  }

  async function checkBrowserHealth() {
    setBrowserHealth("checking")
    try {
      const result = await api.checkBrowserHealth(VENDOR)
      setBrowserHealth(result.ok ? "online" : "offline")
    } catch {
      setBrowserHealth("offline")
    }
  }

  function openArrangeWindowsDialog() {
    setWindowArrangeDraft(windowArrangeSettings)
    setIsArrangeDialogOpen(true)
  }

  function updateWindowArrangeDraft(key: WindowArrangeSettingKey, value: number) {
    setWindowArrangeDraft((current) => ({
      ...current,
      [key]: value,
    }))
  }

  async function arrangeWindows() {
    setError(null)
    setIsArrangingWindows(true)

    const nextSettings = sanitizeWindowArrangeSettings(windowArrangeDraft)

    try {
      await api.arrangeBrowserWindows({
        vendor: VENDOR,
        ...nextSettings,
      })
      saveWindowArrangeSettings(nextSettings)
      setWindowArrangeSettings(nextSettings)
      setWindowArrangeDraft(nextSettings)
      setIsArrangeDialogOpen(false)
    } catch (caught) {
      setError(getErrorMessage(caught))
    } finally {
      setIsArrangingWindows(false)
    }
  }

  async function startRun() {
    if (!selectedTask) {
      return
    }

    setError(null)
    setIsStarting(true)

    try {
      const run = await api.createRun({
        task_key: selectedTask.key,
        vendor: VENDOR,
        concurrency,
        config: configForTask(selectedTask, config),
      })
      setRuns((current) => upsertRun(current, run))
      setLogsByRunId((current) => mergeRunLogs(current, run.id, run.logs))
      setActiveRunId(run.id)
    } catch (caught) {
      setError(getErrorMessage(caught))
    } finally {
      setIsStarting(false)
    }
  }

  async function stopRun() {
    const runId = runningRun?.id
    if (!runId) {
      return
    }

    setError(null)
    setIsStopping(true)

    try {
      const run = await api.stopRun(runId)
      setRuns((current) => upsertRun(current, run))
      setLogsByRunId((current) => mergeRunLogs(current, run.id, run.logs))
      setActiveRunId(run.id)
    } catch (caught) {
      setError(getErrorMessage(caught))
    } finally {
      setIsStopping(false)
    }
  }

  async function saveTaskConfig() {
    if (!selectedTask) {
      return false
    }

    setError(null)
    setIsSavingConfig(true)
    try {
      await api.saveTaskConfiguration(selectedTask.key, configForTask(selectedTask, config))
      return true
    } catch (caught) {
      setError(getErrorMessage(caught))
      return false
    } finally {
      setIsSavingConfig(false)
    }
  }

  function exportTaskConfig() {
    if (!selectedTask) {
      return
    }

    const exportedAt = new Date()
    const payload = {
      task_key: selectedTask.key,
      task_name: selectedTask.name,
      exported_at: exportedAt.toISOString(),
      config: configForTask(selectedTask, config),
    }

    downloadJsonFile(
      `task-config-${selectedTask.key}-${formatDateForFilename(exportedAt)}.json`,
      payload,
    )
  }

  async function importTaskConfig(file: File) {
    if (!selectedTask) {
      return
    }

    setError(null)

    try {
      const parsed = JSON.parse(await file.text()) as unknown
      const importedConfig = parseTaskConfigImport(parsed, selectedTask.key)
      setConfig({
        ...defaultConfigForTask(selectedTask),
        ...configForTask(selectedTask, importedConfig),
      })
    } catch (caught) {
      setError(getErrorMessage(caught))
    }
  }

  async function uploadPluginModule(file: File) {
    setError(null)
    setIsUploadingPlugin(true)

    try {
      await api.uploadPluginModule(file)
      await Promise.all([refreshPluginModules(), refreshTasks()])
    } catch (caught) {
      setError(getErrorMessage(caught))
    } finally {
      setIsUploadingPlugin(false)
    }
  }

  async function reloadPluginModules() {
    setError(null)
    setIsReloadingPlugins(true)

    try {
      const nextPluginModules = await api.reloadPluginModules()
      setPluginModules(nextPluginModules)
      await refreshTasks()
    } catch (caught) {
      setError(getErrorMessage(caught))
    } finally {
      setIsReloadingPlugins(false)
    }
  }

  async function reloadPluginModule(key: string) {
    setError(null)
    setIsReloadingPlugins(true)

    try {
      await api.reloadPluginModule(key)
      await Promise.all([refreshPluginModules(), refreshTasks()])
    } catch (caught) {
      setError(getErrorMessage(caught))
    } finally {
      setIsReloadingPlugins(false)
    }
  }

  async function deletePluginModule(key: string) {
    setError(null)
    setIsReloadingPlugins(true)

    try {
      const nextPluginModules = await api.deletePluginModule(key)
      setPluginModules(nextPluginModules)
      await refreshTasks()
    } catch (caught) {
      setError(getErrorMessage(caught))
    } finally {
      setIsReloadingPlugins(false)
    }
  }

  const content = page === "launcher" ? (
    <section className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[400px_minmax(0,1fr)]">
      <TaskLauncher
        tasks={tasks}
        selectedTask={selectedTask}
        selectedTaskKey={selectedTaskKey}
        concurrency={concurrency}
        config={config}
        runs={runs}
        runningRun={runningRun}
        isStarting={isStarting}
        isStopping={isStopping}
        isSavingConfig={isSavingConfig}
        onTaskChange={setSelectedTaskKey}
        onConcurrencyChange={setConcurrency}
        onConfigChange={setConfig}
        onConfigSave={() => saveTaskConfig()}
        onConfigExport={exportTaskConfig}
        onConfigImport={(file) => void importTaskConfig(file)}
        onStart={() => void startRun()}
        onStop={() => void stopRun()}
      />
      <LogPanel logs={activeLogs} />
    </section>
  ) : page === "records" ? (
    <RunRecords runs={runs} onRefresh={() => void refreshRuns()} />
  ) : (
    <PluginModulesPanel
      modules={pluginModules}
      isUploading={isUploadingPlugin}
      isReloading={isReloadingPlugins}
      onUpload={(file) => void uploadPluginModule(file)}
      onReloadAll={() => void reloadPluginModules()}
      onReload={(key) => void reloadPluginModule(key)}
      onDelete={(key) => void deletePluginModule(key)}
    />
  )

  return (
    <main className="h-screen overflow-hidden bg-background text-foreground">
      <div className="mx-auto flex h-full w-full max-w-[1280px] flex-col gap-4 overflow-hidden px-4 py-4">
        <header className="flex shrink-0 flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-col gap-1">
            <h1 className="text-2xl font-semibold tracking-normal">Helix 自动化控制台</h1>
            <p className="text-sm text-muted-foreground">v{appVersion}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant={page === "launcher" ? "secondary" : "ghost"}
              onClick={() => setPage("launcher")}
            >
              <WorkflowIcon data-icon="inline-start" />
              任务启动
            </Button>
            <Button
              variant={page === "records" ? "secondary" : "ghost"}
              onClick={() => setPage("records")}
            >
              <Rows3Icon data-icon="inline-start" />
              运行记录
            </Button>
            <Button
              variant={page === "modules" ? "secondary" : "ghost"}
              onClick={() => setPage("modules")}
            >
              <PackageIcon data-icon="inline-start" />
              任务插件
            </Button>
            <BrowserHealthBadge status={browserHealth} />
            <Button variant="outline" onClick={() => void checkBrowserHealth()}>
              <RefreshCwIcon data-icon="inline-start" />
              刷新
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button variant="outline">
                    <Settings2Icon data-icon="inline-start" />
                    操作
                    <ChevronDownIcon data-icon="inline-end" />
                  </Button>
                }
              />
              <DropdownMenuContent align="end" className="w-40">
                <DropdownMenuItem onClick={openArrangeWindowsDialog}>
                  <Rows3Icon />
                  重排窗口
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {error ? (
          <Alert variant="destructive" className="shrink-0">
            <AlertTitle>请求失败</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        {content}
      </div>
      <ArrangeWindowsDialog
        open={isArrangeDialogOpen}
        settings={windowArrangeDraft}
        isArranging={isArrangingWindows}
        onOpenChange={setIsArrangeDialogOpen}
        onSettingChange={updateWindowArrangeDraft}
        onSubmit={() => void arrangeWindows()}
      />
      <AutoUpdateDialog />
    </main>
  )
}

interface ArrangeWindowsDialogProps {
  open: boolean
  settings: WindowArrangeSettings
  isArranging: boolean
  onOpenChange: (value: boolean) => void
  onSettingChange: (key: WindowArrangeSettingKey, value: number) => void
  onSubmit: () => void
}

function ArrangeWindowsDialog({
  open,
  settings,
  isArranging,
  onOpenChange,
  onSettingChange,
  onSubmit,
}: ArrangeWindowsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" showCloseButton={!isArranging}>
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            onSubmit()
          }}
        >
          <DialogHeader>
            <DialogTitle>重排窗口</DialogTitle>
            <DialogDescription>Box 模式会按起点、尺寸、列数和间距重新排列当前浏览器窗口。</DialogDescription>
          </DialogHeader>

          <FieldGroup className="grid gap-3 sm:grid-cols-2">
            <WindowArrangeNumberField
              id="window-arrange-start-x"
              label="startX"
              value={settings.startX}
              onChange={(value) => onSettingChange("startX", value)}
            />
            <WindowArrangeNumberField
              id="window-arrange-start-y"
              label="startY"
              value={settings.startY}
              onChange={(value) => onSettingChange("startY", value)}
            />
            <WindowArrangeNumberField
              id="window-arrange-width"
              label="width"
              value={settings.width}
              min={400}
              onChange={(value) => onSettingChange("width", value)}
            />
            <WindowArrangeNumberField
              id="window-arrange-height"
              label="height"
              value={settings.height}
              min={900}
              onChange={(value) => onSettingChange("height", value)}
            />
            <WindowArrangeNumberField
              id="window-arrange-col"
              label="col"
              value={settings.col}
              min={1}
              onChange={(value) => onSettingChange("col", value)}
            />
            <WindowArrangeNumberField
              id="window-arrange-space-x"
              label="spaceX"
              value={settings.spaceX}
              onChange={(value) => onSettingChange("spaceX", value)}
            />
            <WindowArrangeNumberField
              id="window-arrange-space-y"
              label="spaceY"
              value={settings.spaceY}
              onChange={(value) => onSettingChange("spaceY", value)}
            />
          </FieldGroup>

          <DialogFooter>
            <DialogClose render={<Button type="button" variant="outline" disabled={isArranging} />}>
              取消
            </DialogClose>
            <Button type="submit" disabled={isArranging}>
              {isArranging ? "正在重排" : "重排窗口"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

interface WindowArrangeNumberFieldProps {
  id: string
  label: string
  value: number
  min?: number
  onChange: (value: number) => void
}

function WindowArrangeNumberField({
  id,
  label,
  value,
  min,
  onChange,
}: WindowArrangeNumberFieldProps) {
  return (
    <Field className="min-w-0">
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        id={id}
        type="number"
        min={min}
        value={value}
        onChange={(event) => onChange(Number(event.currentTarget.value))}
      />
    </Field>
  )
}

function LogPanel({ logs }: { logs: TaskRunLog[] }) {
  return (
    <Card className="h-full min-h-0">
      <CardHeader>
        <CardTitle>实时日志</CardTitle>
        <CardDescription>按等级显示最近的任务运行日志。</CardDescription>
      </CardHeader>
      <CardContent className="min-h-0 flex-1">
        <LogViewerTerminal
          title="任务运行"
          filterable
          fill
          className="h-full"
          entries={logs.map((log) => ({
            level: log.level,
            message: log.message,
            timestamp: log.timestamp,
          }))}
        />
      </CardContent>
    </Card>
  )
}

interface TaskLauncherProps {
  tasks: TaskModule[]
  selectedTask: TaskModule | undefined
  selectedTaskKey: string
  concurrency: number
  config: Record<string, unknown>
  runs: TaskRun[]
  runningRun: TaskRun | null
  isStarting: boolean
  isStopping: boolean
  isSavingConfig: boolean
  onTaskChange: (value: string) => void
  onConcurrencyChange: (value: number) => void
  onConfigChange: (value: Record<string, unknown>) => void
  onConfigSave: () => Promise<boolean>
  onConfigExport: () => void
  onConfigImport: (file: File) => void
  onStart: () => void
  onStop: () => void
}

function TaskLauncher({
  tasks,
  selectedTask,
  selectedTaskKey,
  concurrency,
  config,
  runs,
  runningRun,
  isStarting,
  isStopping,
  isSavingConfig,
  onTaskChange,
  onConcurrencyChange,
  onConfigChange,
  onConfigSave,
  onConfigExport,
  onConfigImport,
  onStart,
  onStop,
}: TaskLauncherProps) {
  const [isConfigOpen, setIsConfigOpen] = useState(false)
  const [isResultOpen, setIsResultOpen] = useState(false)
  const configBlocks = useMemo(
    () => groupFieldsByBlock(selectedTask?.config_fields ?? []),
    [selectedTask],
  )
  const resultBlocks = selectedTask?.result_blocks ?? []
  const taskResults = useMemo(
    () => collectTaskResults(runs, resultBlocks, selectedTask?.key ?? ""),
    [runs, resultBlocks, selectedTask],
  )
  const blockStats = useMemo(
    () => configBlocks.map((block) => getBlockStats(block, config)),
    [configBlocks, config],
  )

  async function saveAndCloseConfig() {
    const saved = await onConfigSave()
    if (saved) {
      setIsConfigOpen(false)
    }
  }

  return (
    <Card className="h-full min-h-0">
      <CardHeader>
        <CardTitle>任务启动器</CardTitle>
        <CardDescription>选择任务模块并填写运行参数。</CardDescription>
        <CardAction>
          <WorkflowIcon className="text-muted-foreground" />
        </CardAction>
      </CardHeader>
      <CardContent className="min-h-0 overflow-y-auto">
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="task-module">任务模块</FieldLabel>
            <NativeSelect
              id="task-module"
              className="w-full"
              value={selectedTaskKey}
              onChange={(event) => onTaskChange(event.currentTarget.value)}
            >
              {tasks.map((task) => (
                <NativeSelectOption key={task.key} value={task.key}>
                  {task.name}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <FieldDescription>{selectedTask?.description ?? "暂无可用任务模块。"}</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor="concurrency">并发数</FieldLabel>
            <Input
              id="concurrency"
              type="number"
              min={1}
              max={20}
              value={concurrency}
              onChange={(event) => onConcurrencyChange(Number(event.currentTarget.value))}
            />
            <FieldDescription>任务模块按该数量并行创建任务项。</FieldDescription>
          </Field>

          <Separator />

          <div className="flex flex-col gap-3 rounded-lg border p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex flex-col gap-1">
                <div className="text-sm font-medium">任务配置</div>
                
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button variant="outline" onClick={() => setIsConfigOpen(true)} disabled={!selectedTask}>
                  <Settings2Icon data-icon="inline-start" />
                  配置
                </Button>
                {resultBlocks.length > 0 ? (
                  <Button variant="outline" onClick={() => setIsResultOpen(true)} disabled={!selectedTask}>
                    <ReceiptTextIcon data-icon="inline-start" />
                    结果
                  </Button>
                ) : null}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {blockStats.map((block) => (
                <Badge key={block.name} variant={block.missingRequired > 0 ? "outline" : "secondary"}>
                  {block.name} {block.completedRequired}/{block.required}
                </Badge>
              ))}
            </div>
          </div>

          <Button
            onClick={runningRun ? onStop : onStart}
            disabled={isStarting || isStopping || (!runningRun && !selectedTask)}
            variant={runningRun ? "destructive" : "default"}
          >
            {runningRun ? (
              <SquareIcon data-icon="inline-start" />
            ) : (
              <PlayIcon data-icon="inline-start" />
            )}
            {runningRun ? (isStopping ? "正在停止" : "停止任务") : isStarting ? "正在启动" : "启动任务"}
          </Button>
        </FieldGroup>
      </CardContent>
      <TaskConfigSheet
        open={isConfigOpen}
        blocks={configBlocks}
        config={config}
        isSaving={isSavingConfig}
        onOpenChange={setIsConfigOpen}
        onConfigChange={onConfigChange}
        onConfigExport={onConfigExport}
        onConfigImport={onConfigImport}
        onDone={() => void saveAndCloseConfig()}
      />
      <TaskResultSheet
        open={isResultOpen}
        resultBlocks={resultBlocks}
        resultsByBlock={taskResults}
        onOpenChange={setIsResultOpen}
      />
    </Card>
  )
}

interface PluginModulesPanelProps {
  modules: PluginModule[]
  isUploading: boolean
  isReloading: boolean
  onUpload: (file: File) => void
  onReloadAll: () => void
  onReload: (key: string) => void
  onDelete: (key: string) => void
}

function PluginModulesPanel({
  modules,
  isUploading,
  isReloading,
  onUpload,
  onReloadAll,
  onReload,
  onDelete,
}: PluginModulesPanelProps) {
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const busy = isUploading || isReloading

  return (
    <Card className="h-full min-h-0">
      <CardHeader>
        <CardTitle>任务插件</CardTitle>
        <CardDescription>已安装的动态任务模块。</CardDescription>
        <CardAction>
          <div className="flex items-center gap-2">
            <input
              ref={uploadInputRef}
              type="file"
              accept="application/zip,.zip"
              className="sr-only"
              onChange={(event) => {
                const file = event.currentTarget.files?.[0]
                event.currentTarget.value = ""
                if (file) {
                  onUpload(file)
                }
              }}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => uploadInputRef.current?.click()}
              disabled={busy}
            >
              <UploadIcon data-icon="inline-start" />
              {isUploading ? "正在上传" : "上传插件包"}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onReloadAll}
              disabled={busy}
            >
              <RefreshCwIcon data-icon="inline-start" />
              重载
            </Button>
          </div>
        </CardAction>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-y-auto">
        {modules.length === 0 ? (
          <Alert>
            <PackageIcon />
            <AlertTitle>暂无插件</AlertTitle>
            <AlertDescription>上传插件包后会显示在这里。</AlertDescription>
          </Alert>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>模块</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>入口</TableHead>
                <TableHead>版本</TableHead>
                <TableHead>错误</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {modules.map((module) => (
                <TableRow key={module.key}>
                  <TableCell>
                    <div className="flex min-w-0 flex-col gap-1">
                      <span className="font-medium">{module.name || module.key}</span>
                      <span className="font-mono text-xs text-muted-foreground">{module.key}</span>
                      {module.description ? (
                        <span className="max-w-96 truncate text-xs text-muted-foreground">
                          {module.description}
                        </span>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={module.status} />
                  </TableCell>
                  <TableCell className="font-mono text-xs">{module.entry || "-"}</TableCell>
                  <TableCell>{module.version || "-"}</TableCell>
                  <TableCell className="max-w-96 truncate text-xs text-muted-foreground">
                    {module.error || "-"}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => onReload(module.key)}
                        disabled={busy}
                        aria-label={`重载 ${module.key}`}
                      >
                        <RefreshCwIcon />
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => onDelete(module.key)}
                        disabled={busy}
                        aria-label={`删除 ${module.key}`}
                      >
                        <Trash2Icon />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

interface TaskConfigBlock {
  name: string
  fields: TaskConfigField[]
}

interface TaskConfigSheetProps {
  open: boolean
  blocks: TaskConfigBlock[]
  config: Record<string, unknown>
  isSaving: boolean
  onOpenChange: (value: boolean) => void
  onConfigChange: (value: Record<string, unknown>) => void
  onConfigExport: () => void
  onConfigImport: (file: File) => void
  onDone: () => void
}

function TaskConfigSheet({
  open,
  blocks,
  config,
  isSaving,
  onOpenChange,
  onConfigChange,
  onConfigExport,
  onConfigImport,
  onDone,
}: TaskConfigSheetProps) {
  const [activeBlockName, setActiveBlockName] = useState("")
  const importInputRef = useRef<HTMLInputElement>(null)
  const activeBlock = blocks.find((block) => block.name === activeBlockName) ?? blocks[0]

  useEffect(() => {
    if (!activeBlockName && blocks[0]) {
      setActiveBlockName(blocks[0].name)
      return
    }

    if (activeBlockName && !blocks.some((block) => block.name === activeBlockName)) {
      setActiveBlockName(blocks[0]?.name ?? "")
    }
  }, [activeBlockName, blocks])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="overflow-hidden"
        style={{ width: "min(96vw, 960px)", maxWidth: "96vw" }}
      >
        <SheetHeader>
          <SheetTitle>任务配置</SheetTitle>
          <SheetDescription>当前任务的分组运行参数。</SheetDescription>
        </SheetHeader>

        <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto px-4 pb-2 xl:grid-cols-[200px_minmax(0,1fr)]">
          <nav className="flex min-w-0 gap-2 overflow-x-auto xl:flex-col xl:overflow-x-visible">
            {blocks.map((block) => {
              const stats = getBlockStats(block, config)
              const isActive = block.name === activeBlock?.name

              return (
                <Button
                  key={block.name}
                  type="button"
                  variant={isActive ? "secondary" : "ghost"}
                  className="h-auto min-w-32 justify-between px-2 py-2 xl:w-full"
                  onClick={() => setActiveBlockName(block.name)}
                >
                  <span className="truncate">{block.name}</span>
                  <Badge variant={stats.missingRequired > 0 ? "outline" : "secondary"}>
                    {stats.completedRequired}/{stats.required}
                  </Badge>
                </Button>
              )
            })}
          </nav>

          <div className="min-w-0 rounded-lg border">
            {activeBlock ? (
              <FieldSet className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex flex-col gap-1">
                    <div className="text-base font-medium">{activeBlock.name}</div>
                    <div className="text-sm text-muted-foreground">
                      {activeBlock.fields.length} 个字段 · 缺少 {getBlockStats(activeBlock, config).missingRequired} 个必填项
                    </div>
                  </div>
                  <Badge variant="outline">{activeBlock.fields.length}</Badge>
                </div>
                <Separator />
                <FieldGroup>
                  {activeBlock.fields.map((field) => (
                    <TaskConfigControl
                      key={field.key}
                      field={field}
                      value={config[field.key]}
                      onChange={(value) =>
                        onConfigChange({
                          ...config,
                          [field.key]: value,
                        })
                      }
                    />
                  ))}
                </FieldGroup>
              </FieldSet>
            ) : (
              <div className="p-4 text-sm text-muted-foreground">暂无配置分组。</div>
            )}
          </div>
        </div>

        <SheetFooter>
          <div className="flex flex-1 items-center gap-2">
            <input
              ref={importInputRef}
              type="file"
              accept="application/json,.json"
              className="sr-only"
              onChange={(event) => {
                const file = event.currentTarget.files?.[0]
                event.currentTarget.value = ""
                if (file) {
                  onConfigImport(file)
                }
              }}
            />
            <Button type="button" variant="outline" onClick={onConfigExport} disabled={blocks.length === 0}>
              <DownloadIcon data-icon="inline-start" />
              导出
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => importInputRef.current?.click()}
              disabled={blocks.length === 0}
            >
              <UploadIcon data-icon="inline-start" />
              导入
            </Button>
          </div>
          <Button onClick={onDone} disabled={isSaving}>
            {isSaving ? "正在保存" : "完成"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

interface TaskResultSheetProps {
  open: boolean
  resultBlocks: TaskResultBlock[]
  resultsByBlock: Record<string, TaskResultGroup[]>
  onOpenChange: (value: boolean) => void
}

function TaskResultSheet({
  open,
  resultBlocks,
  resultsByBlock,
  onOpenChange,
}: TaskResultSheetProps) {
  const [activeBlockKey, setActiveBlockKey] = useState("")
  const activeBlock = resultBlocks.find((block) => block.key === activeBlockKey) ?? resultBlocks[0]

  useEffect(() => {
    if (!activeBlockKey && resultBlocks[0]) {
      setActiveBlockKey(resultBlocks[0].key)
      return
    }

    if (activeBlockKey && !resultBlocks.some((block) => block.key === activeBlockKey)) {
      setActiveBlockKey(resultBlocks[0]?.key ?? "")
    }
  }, [activeBlockKey, resultBlocks])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="overflow-hidden"
        style={{ width: "min(96vw, 960px)", maxWidth: "96vw" }}
      >
        <SheetHeader>
          <SheetTitle>任务结果</SheetTitle>
          <SheetDescription>任务 manifest 声明的本地数据库结果。</SheetDescription>
        </SheetHeader>

        <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto px-4 pb-2 xl:grid-cols-[200px_minmax(0,1fr)]">
          <nav className="flex min-w-0 gap-2 overflow-x-auto xl:flex-col xl:overflow-x-visible">
            {resultBlocks.map((block) => {
              const isActive = block.key === activeBlock?.key
              const count = countGroupedResults(resultsByBlock[block.key] ?? [])

              return (
                <Button
                  key={block.key}
                  type="button"
                  variant={isActive ? "secondary" : "ghost"}
                  className="h-auto min-w-32 justify-between px-2 py-2 xl:w-full"
                  onClick={() => setActiveBlockKey(block.key)}
                >
                  <span className="truncate">{block.label}</span>
                  <Badge variant="secondary">{count}</Badge>
                </Button>
              )
            })}
          </nav>

          <div className="min-w-0 rounded-lg border p-4">
            {activeBlock ? (
              <TaskResultPanel
                block={activeBlock}
                results={resultsByBlock[activeBlock.key] ?? []}
              />
            ) : (
              <Alert>
                <AlertTitle>暂无结果面板</AlertTitle>
                <AlertDescription>当前任务 manifest 没有声明 result blocks。</AlertDescription>
              </Alert>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function TaskResultPanel({ block, results }: { block: TaskResultBlock; results: TaskResultGroup[] }) {
  const total = countGroupedResults(results)

  return (
    <section className="flex min-w-0 flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="text-base font-medium">{block.label}</div>
          <div className="text-sm text-muted-foreground">
            {block.description || "本地运行产生的任务结果记录。"}
          </div>
        </div>
        <Badge variant="secondary">{total} 条</Badge>
      </div>

      {total === 0 ? (
        <Alert>
          <AlertTitle>暂无支付结果</AlertTitle>
          <AlertDescription>任务提交 cards 后会在这里显示结果。</AlertDescription>
        </Alert>
      ) : (
        <div className="flex min-w-0 flex-col gap-4">
          {results.map((group) => (
            <section key={group.runId} className="min-w-0 rounded-lg border">
              <div className="flex items-start justify-between gap-3 border-b bg-muted/30 px-3 py-2">
                <div className="flex min-w-0 flex-col gap-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{formatRunResultTitle(group)}</span>
                    <StatusBadge status={group.status} />
                    <Badge variant="secondary">{group.results.length} 条</Badge>
                  </div>
                  <span className="truncate font-mono text-xs text-muted-foreground">{group.runId}</span>
                </div>
                <div className="shrink-0 text-xs text-muted-foreground">
                  {formatDateTime(group.createdAt)}
                </div>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>状态</TableHead>
                    <TableHead>卡号</TableHead>
                    <TableHead>任务项</TableHead>
                    <TableHead>时间</TableHead>
                    <TableHead>消息</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {group.results.map((result, index) => (
                    <TableRow key={`${group.runId}-${formatResultValue(result.id)}-${index}`}>
                      <TableCell>
                        <StatusBadge status={formatResultValue(result.status)} />
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {formatPaymentCard(result)}
                      </TableCell>
                      <TableCell>{formatResultValue(result.item_index)}</TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatResultTime(result)}
                      </TableCell>
                      <TableCell className="max-w-80 truncate">
                        {formatResultValue(result.message)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </section>
          ))}
        </div>
      )}
    </section>
  )
}

interface TaskConfigControlProps {
  field: TaskConfigField
  value: unknown
  onChange: (value: unknown) => void
}

function TaskConfigControl({ field, value, onChange }: TaskConfigControlProps) {
  const id = `task-config-${field.key}`
  const stringValue = value === undefined || value === null ? "" : String(value)
  const lineCount = field.key === "cards" ? countNonEmptyLines(stringValue) : null
  const description = field.key === "cards"
    ? `${field.description ? `${field.description} ` : ""}当前 ${lineCount ?? 0} 行。`
    : field.description

  return (
    <Field className="min-w-0">
      <FieldLabel htmlFor={id} className="flex-wrap">
        <span className="min-w-0 break-words">{field.label}</span>
        {lineCount !== null ? <Badge variant="secondary">{lineCount} 行</Badge> : null}
        {field.required ? <Badge variant="outline">必填</Badge> : null}
      </FieldLabel>
      {field.field_type === "textarea" ? (
        <Textarea
          id={id}
          value={stringValue}
          placeholder={field.placeholder}
          onChange={(event) => onChange(event.currentTarget.value)}
          className="min-h-24 resize-y"
        />
      ) : field.field_type === "select" ? (
        <NativeSelect
          id={id}
          className="w-full"
          value={stringValue}
          onChange={(event) => onChange(event.currentTarget.value)}
        >
          {field.options.map((option) => (
            <NativeSelectOption key={option} value={option}>
              {option}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      ) : field.field_type === "multi-select" ? (
        <TaskConfigMultiSelect
          field={field}
          value={value}
          onChange={onChange}
        />
      ) : field.field_type === "checkbox" ? (
        <div className="flex items-center gap-3">
          <Switch
            id={id}
            checked={normalizeBooleanValue(value)}
            onCheckedChange={(checked) => onChange(Boolean(checked))}
          />
          <span className="text-sm text-muted-foreground">
            {normalizeBooleanValue(value) ? "开启" : "关闭"}
          </span>
        </div>
      ) : (
        <Input
          id={id}
          type={field.field_type === "password" ? "password" : field.field_type === "number" ? "number" : "text"}
          value={stringValue}
          placeholder={field.placeholder}
          onChange={(event) => onChange(field.field_type === "number" ? Number(event.currentTarget.value) : event.currentTarget.value)}
        />
      )}
      {description ? <FieldDescription className="break-words">{description}</FieldDescription> : null}
    </Field>
  )
}

function TaskConfigMultiSelect({
  field,
  value,
  onChange,
}: TaskConfigControlProps) {
  const selectedValues = normalizeMultiSelectValue(value)
  const collection = createListCollection({
    items: field.options.map((option) => ({
      label: option,
      value: option,
    })),
  })

  return (
    <Select
      collection={collection}
      value={selectedValues}
      onValueChange={(details) => onChange(details.value)}
      multiple
    >
      <SelectTrigger className="w-full">
        <SelectValue>
          <SelectContext>{({ value }) => renderMultiSelectValue(value)}</SelectContext>
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {collection.items.map((item) => (
          <SelectItem item={item} key={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function RunRecords({ runs, onRefresh }: { runs: TaskRun[]; onRefresh: () => void }) {
  return (
    <Card className="h-full min-h-0">
      <CardHeader>
        <CardTitle>运行记录</CardTitle>
        <CardDescription>每次任务运行都会记录浏览器窗口和任务项状态。</CardDescription>
        <CardAction>
          <Button variant="outline" size="sm" onClick={onRefresh}>
            <RefreshCwIcon data-icon="inline-start" />
            刷新
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-4">
          {runs.length === 0 ? (
            <Alert>
              <Rows3Icon />
              <AlertTitle>暂无运行记录</AlertTitle>
              <AlertDescription>启动任务后会在这里看到持久化的运行记录。</AlertDescription>
            </Alert>
          ) : (
            runs.map((run) => <RunRecord key={run.id} run={run} />)
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function RunRecord({ run }: { run: TaskRun }) {
  const progress = run.total === 0 ? 0 : Math.round(((run.completed + run.failed) / run.total) * 100)
  const resultJson = run.result_json ?? []

  return (
    <section className="flex flex-col gap-3 rounded-lg border p-3">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{run.task_name}</span>
            <StatusBadge status={run.status} />
            <Badge variant="secondary">{run.vendor}</Badge>
          </div>
          <p className="truncate text-sm text-muted-foreground">{run.id}</p>
        </div>
        <div className="text-sm text-muted-foreground">
          已完成 {run.completed}/{run.total} · 失败 {run.failed} · 并发 {run.concurrency}
        </div>
      </div>

      <Progress value={progress} />

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>任务项</TableHead>
            <TableHead>窗口 ID</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>调试地址</TableHead>
            <TableHead>PID</TableHead>
            <TableHead>消息</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {run.items.map((item) => (
            <TableRow key={item.id}>
              <TableCell>{item.item_index}</TableCell>
              <TableCell className="font-mono text-xs">{item.profile_id ?? "-"}</TableCell>
              <TableCell>
                <StatusBadge status={item.status} />
              </TableCell>
              <TableCell className="font-mono text-xs">{item.debug_address ?? "-"}</TableCell>
              <TableCell>{item.pid ?? "-"}</TableCell>
              <TableCell className="max-w-72 truncate">{item.error ?? item.message ?? "-"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {resultJson.length > 0 ? (
        <>
          <Separator />
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-medium">结果记录</div>
              <Badge variant="secondary">{resultJson.length} 条</Badge>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>任务项</TableHead>
                  <TableHead>键名</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>时间</TableHead>
                  <TableHead>原始行</TableHead>
                  <TableHead>消息</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resultJson.map((result, index) => (
                  <TableRow key={String(result.id ?? index)}>
                    <TableCell>{formatResultValue(result.item_index)}</TableCell>
                    <TableCell className="font-mono text-xs">{formatResultValue(result.key)}</TableCell>
                    <TableCell>
                      <StatusBadge status={formatResultValue(result.status)} />
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatResultTime(result)}
                    </TableCell>
                    <TableCell className="max-w-72 truncate font-mono text-xs">
                      {formatResultValue(result.line)}
                    </TableCell>
                    <TableCell className="max-w-72 truncate">
                      {formatResultValue(result.message)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      ) : null}
    </section>
  )
}

function BrowserHealthBadge({ status }: { status: "checking" | "online" | "offline" }) {
  const variant = status === "online" ? "default" : status === "offline" ? "destructive" : "secondary"

  return (
    <Badge variant={variant}>
      <ActivityIcon data-icon="inline-start" />
      BitBrowser {formatStatusLabel(status)}
    </Badge>
  )
}

function StatusBadge({ status }: { status: string }) {
  const variant = ["failed", "error"].includes(status) ? "destructive" : ["completed", "loaded", "online", "success"].includes(status) ? "default" : "secondary"

  return <Badge variant={variant}>{formatStatusLabel(status)}</Badge>
}

function formatStatusLabel(status: string) {
  const labels: Record<string, string> = {
    add_different_card: "需要换卡",
    checking: "检查中",
    completed: "已完成",
    error: "错误",
    failed: "失败",
    loaded: "已加载",
    offline: "离线",
    online: "在线",
    pending: "等待中",
    payment_issue: "支付异常",
    running: "运行中",
    stopped: "已停止",
    stopping: "停止中",
    success: "成功",
    timeout: "超时",
    validation_error: "校验失败",
  }

  return labels[status] ?? status
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

function loadWindowArrangeSettings(): WindowArrangeSettings {
  try {
    const rawValue = window.localStorage.getItem(WINDOW_ARRANGE_STORAGE_KEY)
    if (!rawValue) {
      return DEFAULT_WINDOW_ARRANGE_SETTINGS
    }

    const parsed = JSON.parse(rawValue) as unknown
    if (!isRecord(parsed)) {
      return DEFAULT_WINDOW_ARRANGE_SETTINGS
    }

    return sanitizeWindowArrangeSettings({
      ...DEFAULT_WINDOW_ARRANGE_SETTINGS,
      ...Object.fromEntries(
        Object.entries(parsed).map(([key, value]) => [key, normalizeWindowArrangeNumber(value)]),
      ),
    })
  } catch {
    return DEFAULT_WINDOW_ARRANGE_SETTINGS
  }
}

function saveWindowArrangeSettings(settings: WindowArrangeSettings) {
  window.localStorage.setItem(WINDOW_ARRANGE_STORAGE_KEY, JSON.stringify(settings))
}

function sanitizeWindowArrangeSettings(settings: WindowArrangeSettings): WindowArrangeSettings {
  return {
    startX: normalizeWindowArrangeNumber(settings.startX),
    startY: normalizeWindowArrangeNumber(settings.startY),
    width: Math.max(normalizeWindowArrangeNumber(settings.width), 400),
    height: Math.max(normalizeWindowArrangeNumber(settings.height), 900),
    col: Math.max(normalizeWindowArrangeNumber(settings.col), 1),
    spaceX: normalizeWindowArrangeNumber(settings.spaceX),
    spaceY: normalizeWindowArrangeNumber(settings.spaceY),
  }
}

function normalizeWindowArrangeNumber(value: unknown) {
  const numberValue = typeof value === "number" ? value : Number(value)
  return Number.isFinite(numberValue) ? Math.trunc(numberValue) : 0
}

function isBackendConnectionMessage(message: string | null) {
  return ["后端正在启动，请稍候。", "程序正在启动，请稍候。", "应用正在启动，请稍候。", "运行状态连接失败。"].includes(message ?? "")
}

async function waitForApiReady() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const health = await api.checkApiHealth()
      if (health.ok) {
        return true
      }
    } catch {
      await delay(1000)
    }
  }
  return false
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function downloadJsonFile(filename: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }))
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

function parseTaskConfigImport(value: unknown, currentTaskKey: string) {
  if (!isRecord(value)) {
    throw new Error("导入的任务配置必须是 JSON 对象。")
  }

  if (isTaskConfigExport(value)) {
    if (typeof value.task_key === "string" && value.task_key !== currentTaskKey) {
      throw new Error(`导入的配置属于任务 "${value.task_key}"，不是当前任务 "${currentTaskKey}"。`)
    }

    if (!isRecord(value.config)) {
      throw new Error("导入的任务配置缺少有效的 config 对象。")
    }

    return value.config
  }

  return value
}

function isTaskConfigExport(value: Record<string, unknown>) {
  return "config" in value && (
    "task_key" in value ||
    "task_name" in value ||
    "exported_at" in value
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function formatDateForFilename(date: Date) {
  return date.toISOString().replace(/[:.]/g, "-")
}

function groupFieldsByBlock(fields: TaskConfigField[]): TaskConfigBlock[] {
  const grouped = new Map<string, TaskConfigField[]>()
  for (const field of fields) {
    const block = normalizeBlockName(field)
    grouped.set(block, [...(grouped.get(block) ?? []), field])
  }

  return Array.from(grouped.entries()).map(([name, blockFields]) => ({
    name,
    fields: blockFields,
  }))
}

function normalizeBlockName(field: TaskConfigField) {
  if (field.block && field.block !== "general") {
    return field.block
  }

  if (field.key.startsWith("cloud_mail_")) {
    return "邮箱"
  }
  if (field.key.includes("proxy")) {
    return "代理"
  }
  if (["coreVersion", "core_version", "ostype"].includes(field.key)) {
    return "浏览器"
  }
  if (field.key.includes("account")) {
    return "账号"
  }
  return "任务"
}

function getBlockStats(block: TaskConfigBlock, config: Record<string, unknown>) {
  const requiredFields = block.fields.filter((field) => field.required)
  const completedRequired = requiredFields.filter((field) => isFilled(config[field.key])).length

  return {
    name: block.name,
    required: requiredFields.length,
    completedRequired,
    missingRequired: requiredFields.length - completedRequired,
  }
}

function isFilled(value: unknown) {
  if (typeof value === "string") {
    return value.trim().length > 0
  }
  if (Array.isArray(value)) {
    return value.length > 0
  }
  return value !== undefined && value !== null && value !== ""
}

function normalizeMultiSelectValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item))
  }
  if (typeof value === "string" && value.trim()) {
    return value.split(",").map((item) => item.trim()).filter(Boolean)
  }
  return []
}

function normalizeBooleanValue(value: unknown) {
  if (typeof value === "boolean") {
    return value
  }
  if (typeof value === "string") {
    return ["1", "true", "yes", "on", "y"].includes(value.trim().toLowerCase())
  }
  return Boolean(value)
}

function countNonEmptyLines(value: string) {
  return value.split(/\r?\n/).filter((line) => line.trim().length > 0).length
}

function renderMultiSelectValue(value: string[]) {
  if (value.length === 0) {
    return "请选择"
  }

  const firstValue = value[0] ?? ""
  const additionalValues = value.length > 1 ? `（另 ${value.length - 1} 项）` : ""
  return firstValue + additionalValues
}

function formatResultValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "-"
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value)
  }
  return JSON.stringify(value)
}

function formatResultTime(result: Record<string, unknown>) {
  const value = result.finished_at ?? result.reserved_at ?? result.created_at ?? result.time
  if (typeof value !== "string" || !value) {
    return "-"
  }

  return formatDateTime(value)
}

function formatDateTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString()
}

function collectTaskResults(
  runs: TaskRun[],
  resultBlocks: TaskResultBlock[],
  taskKey: string,
): Record<string, TaskResultGroup[]> {
  return Object.fromEntries(
    resultBlocks.map((block) => [
      block.key,
      runs
        .filter((run) => run.task_key === taskKey)
        .map((run) => ({
          runId: run.id,
          taskName: run.task_name,
          status: run.status,
          createdAt: run.created_at,
          results: (run.result_json ?? [])
            .filter((result) => result.key === block.source_key)
            .map((result) => ({
              ...result,
              run_id: run.id,
              run_status: run.status,
              run_created_at: run.created_at,
            }))
            .sort((left, right) => Date.parse(formatRawResultTime(right)) - Date.parse(formatRawResultTime(left))),
        }))
        .filter((group) => group.results.length > 0)
        .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt)),
    ]),
  )
}

function countGroupedResults(groups: TaskResultGroup[]) {
  return groups.reduce((total, group) => total + group.results.length, 0)
}

function formatRunResultTitle(group: TaskResultGroup) {
  return group.taskName || "任务执行"
}

function formatPaymentCard(result: TaskResult) {
  const cardNumber = result.card_last4
  if (typeof cardNumber === "string" && cardNumber) {
    return cardNumber
  }

  return formatResultValue(result.line)
}

function formatRawResultTime(result: Record<string, unknown>) {
  const value = result.finished_at ?? result.reserved_at ?? result.created_at ?? result.run_created_at ?? result.time
  return typeof value === "string" ? value : ""
}

function isRunActive(run: TaskRun) {
  return ["pending", "running", "stopping"].includes(run.status)
}

function defaultConfigForTask(task: TaskModule) {
  const defaults: Record<string, unknown> = {}
  for (const field of task.config_fields) {
    if (field.default !== null && field.default !== undefined) {
      defaults[field.key] = field.default
    }
  }
  return defaults
}

function configForTask(task: TaskModule, config: Record<string, unknown>) {
  const allowedKeys = new Set(task.config_fields.map((field) => field.key))
  return Object.fromEntries(
    Object.entries(config).filter(([key]) => allowedKeys.has(key)),
  )
}

function upsertRun(runs: TaskRun[], run: TaskRun) {
  const next = runs.some((item) => item.id === run.id)
    ? runs.map((item) => (item.id === run.id ? run : item))
    : [run, ...runs]

  return next.sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
}

function mergeRunLogs(
  logsByRunId: Record<string, TaskRunLog[]>,
  runId: string,
  logs: TaskRunLog[],
) {
  if (logs.length === 0) {
    return logsByRunId[runId] ? logsByRunId : { ...logsByRunId, [runId]: [] }
  }

  const current = logsByRunId[runId] ?? []
  const indexById = new Map(current.map((log, index) => [log.id, index]))
  const nextLogs = [...current]

  for (const log of logs) {
    const existingIndex = indexById.get(log.id)
    if (existingIndex === undefined) {
      indexById.set(log.id, nextLogs.length)
      nextLogs.push(log)
    } else {
      nextLogs[existingIndex] = log
    }
  }

  return {
    ...logsByRunId,
    [runId]: nextLogs.sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp)),
  }
}

function closeWebSocket(socket: WebSocket) {
  if (socket.readyState === WebSocket.CONNECTING) {
    socket.onopen = () => socket.close()
    return
  }

  if (socket.readyState === WebSocket.OPEN) {
    socket.close()
  }
}

export default App
