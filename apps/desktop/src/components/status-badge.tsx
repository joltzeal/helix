import { ActivityIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"

export function BrowserHealthBadge({
  label = "BitBrowser",
  status,
}: {
  label?: string
  status: "checking" | "online" | "offline"
}) {
  const variant = status === "online" ? "default" : status === "offline" ? "destructive" : "secondary"

  return (
    <Badge variant={variant}>
      <ActivityIcon data-icon="inline-start" />
      {label} {formatStatusLabel(status)}
    </Badge>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const variant = ["failed", "error"].includes(status)
    ? "destructive"
    : ["completed", "loaded", "online", "success"].includes(status)
      ? "default"
      : "secondary"

  return <Badge variant={variant}>{formatStatusLabel(status)}</Badge>
}

export function formatStatusLabel(status: string) {
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
