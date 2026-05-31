import { RefreshCwIcon, Rows3Icon } from "lucide-react"

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
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { StatusBadge } from "@/components/status-badge"
import type { TaskRun } from "@/lib/api"

export function RunRecords({ runs, onRefresh }: { runs: TaskRun[]; onRefresh: () => void }) {
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
  const rawValue = result.created_at ?? result.timestamp ?? result.time
  if (typeof rawValue !== "string" || rawValue.length === 0) {
    return "-"
  }
  return formatDateTime(rawValue)
}

function formatDateTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(date)
}
