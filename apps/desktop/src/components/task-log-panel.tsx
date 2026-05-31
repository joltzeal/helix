import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { LogViewerTerminal } from "@/components/log-viewer"
import type { TaskRunLog } from "@/lib/api"

export function TaskLogPanel({ logs }: { logs: TaskRunLog[] }) {
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
