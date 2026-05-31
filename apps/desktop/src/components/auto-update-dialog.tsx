import { isTauri } from "@tauri-apps/api/core"
import { relaunch } from "@tauri-apps/plugin-process"
import { check, type DownloadEvent, type Update } from "@tauri-apps/plugin-updater"
import { DownloadIcon, RefreshCwIcon } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Progress } from "@/components/ui/progress"

type UpdateStatus = "available" | "downloading" | "installing" | "restarting" | "failed"
export type UpdateCheckResult = "available" | "none" | "unavailable" | "failed"

interface DownloadProgress {
  downloaded: number
  total?: number
}

interface AutoUpdateDialogProps {
  checkRequestId?: number
  onManualCheckComplete?: (result: UpdateCheckResult, message: string) => void
}

export function AutoUpdateDialog({
  checkRequestId = 0,
  onManualCheckComplete,
}: AutoUpdateDialogProps) {
  const [open, setOpen] = useState(false)
  const [update, setUpdate] = useState<Update | null>(null)
  const [status, setStatus] = useState<UpdateStatus>("available")
  const [progress, setProgress] = useState<DownloadProgress>({ downloaded: 0 })
  const [error, setError] = useState<string | null>(null)
  const lastManualCheckRequestRef = useRef(checkRequestId)

  const isBusy = status === "downloading" || status === "installing" || status === "restarting"
  const progressValue = progress.total
    ? Math.min(100, Math.round((progress.downloaded / progress.total) * 100))
    : status === "installing" || status === "restarting"
      ? 100
      : 0

  useEffect(() => {
    let disposed = false

    void checkForUpdate({ manual: false, isDisposed: () => disposed })

    return () => {
      disposed = true
    }
  }, [])

  useEffect(() => {
    if (checkRequestId <= 0 || checkRequestId === lastManualCheckRequestRef.current) {
      return
    }

    lastManualCheckRequestRef.current = checkRequestId
    let disposed = false

    void checkForUpdate({
      manual: true,
      isDisposed: () => disposed,
      onComplete: onManualCheckComplete,
    })

    return () => {
      disposed = true
    }
  }, [checkRequestId, onManualCheckComplete])

  useEffect(() => {
    return () => {
      if (update) {
        void update.close()
      }
    }
  }, [update])

  async function installUpdate() {
    if (!update || isBusy) {
      return
    }

    try {
      setError(null)
      setStatus("downloading")
      setProgress({ downloaded: 0 })
      await update.download(handleDownloadEvent)
      setStatus("installing")
      await update.install()
      setStatus("restarting")
      await relaunch()
    } catch (caught) {
      setStatus("failed")
      setError(getErrorMessage(caught))
    }
  }

  async function checkForUpdate({
    manual,
    isDisposed,
    onComplete,
  }: {
    manual: boolean
    isDisposed: () => boolean
    onComplete?: (result: UpdateCheckResult, message: string) => void
  }) {
    if (!isTauri() || import.meta.env.DEV) {
      if (manual && !isDisposed()) {
        onComplete?.("unavailable", "当前环境不支持更新检测。")
      }
      return
    }

    try {
      const availableUpdate = await check()
      if (isDisposed()) {
        availableUpdate?.close()
        return
      }

      if (availableUpdate) {
        setUpdate(availableUpdate)
        setStatus("available")
        setError(null)
        setProgress({ downloaded: 0 })
        setOpen(true)
        if (manual) {
          onComplete?.("available", `发现新版本 ${availableUpdate.version}。`)
        }
        return
      }

      if (manual) {
        onComplete?.("none", "当前已是最新版本。")
      }
    } catch (caught) {
      console.warn("Failed to check for updates", caught)
      if (manual && !isDisposed()) {
        onComplete?.("failed", getErrorMessage(caught))
      }
    }
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!isBusy) {
      setOpen(nextOpen)
    }
  }

  function handleDownloadEvent(event: DownloadEvent) {
    if (event.event === "Started") {
      setProgress({ downloaded: 0, total: event.data.contentLength })
      return
    }

    if (event.event === "Progress") {
      setProgress((current) => ({
        downloaded: current.downloaded + event.data.chunkLength,
        total: current.total,
      }))
      return
    }

    setProgress((current) => ({
      downloaded: current.total ?? current.downloaded,
      total: current.total,
    }))
  }

  if (!update) {
    return null
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent showCloseButton={!isBusy}>
        <DialogHeader>
          <DialogTitle>发现新版本 {update.version}</DialogTitle>
          <DialogDescription>
            当前版本 {update.currentVersion}，更新包将自动下载并在安装完成后重启应用。
          </DialogDescription>
        </DialogHeader>

        {update.body ? (
          <div className="max-h-36 overflow-y-auto rounded-lg border bg-muted/30 p-3 text-sm whitespace-pre-wrap">
            {update.body}
          </div>
        ) : null}

        {status !== "available" ? (
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span>{statusText(status)}</span>
              {status === "downloading" && progress.total ? (
                <span className="text-muted-foreground tabular-nums">{progressValue}%</span>
              ) : null}
            </div>
            <Progress value={progressValue} />
          </div>
        ) : null}

        {error ? (
          <p className="text-sm text-destructive">更新失败：{error}</p>
        ) : null}

        <DialogFooter>
          {!isBusy ? (
            <Button variant="outline" onClick={() => setOpen(false)}>
              稍后
            </Button>
          ) : null}
          <Button onClick={() => void installUpdate()} disabled={isBusy}>
            {isBusy ? (
              <RefreshCwIcon data-icon="inline-start" />
            ) : (
              <DownloadIcon data-icon="inline-start" />
            )}
            {status === "failed" ? "重试更新" : isBusy ? statusText(status) : "立即更新"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function statusText(status: UpdateStatus) {
  switch (status) {
    case "downloading":
      return "正在下载"
    case "installing":
      return "正在安装"
    case "restarting":
      return "正在重启"
    case "failed":
      return "更新失败"
    case "available":
      return "可更新"
  }
}

function getErrorMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}
