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
  const progress =
    run.total === 0 ? 0 : Math.round(((run.completed + run.failed + run.cancelled) / run.total) * 100)

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
            <TableHead>键名</TableHead>
            <TableHead>标签</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>开始时间</TableHead>
            <TableHead>结束时间</TableHead>
            <TableHead>消息</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {run.items.map((item) => (
            <TableRow key={item.id}>
              <TableCell>{item.index}</TableCell>
              <TableCell className="font-mono text-xs">{item.key}</TableCell>
              <TableCell className="max-w-48 truncate">{item.label}</TableCell>
              <TableCell>
                <StatusBadge status={item.status} />
              </TableCell>
              <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                {item.started_at ? formatDateTime(item.started_at) : "-"}
              </TableCell>
              <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                {item.finished_at ? formatDateTime(item.finished_at) : "-"}
              </TableCell>
              <TableCell className="max-w-72 truncate">{item.error ?? item.message ?? "-"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  )
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
