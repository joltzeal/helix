import { useRef } from "react"
import { PackageIcon, RefreshCwIcon, Trash2Icon, UploadIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { StatusBadge } from "@/components/status-badge"
import type { PluginModule } from "@/lib/api"

interface PluginModulesPanelProps {
  modules: PluginModule[]
  isUploading: boolean
  isReloading: boolean
  onUpload: (file: File) => void
  onReloadAll: () => void
  onReload: (key: string) => void
  onDelete: (key: string) => void
}

export function PluginModulesPanel({
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
