import { useCallback, useState } from "react"

import { api } from "@/lib/api"

const API_READY_ATTEMPTS = 60
const API_READY_INTERVAL_MS = 1000

export const API_STARTING_MESSAGE = "程序正在启动，请稍候。"
export const API_START_TIMEOUT_MESSAGE = "程序启动超时，请重启应用。"

interface UseApiReadyOptions {
  onStarting: () => void
  onReady: () => void
  onTimeout: () => void
}

export function useApiReady({
  onStarting,
  onReady,
  onTimeout,
}: UseApiReadyOptions) {
  const [apiReady, setApiReady] = useState(false)

  const checkApiReady = useCallback(async () => {
    onStarting()

    const ready = await waitForApiReady()
    setApiReady(ready)

    if (ready) {
      onReady()
    } else {
      onTimeout()
    }
  }, [onReady, onStarting, onTimeout])

  return { apiReady, checkApiReady }
}

export function isBackendConnectionMessage(message: string | null) {
  return [
    "后端正在启动，请稍候。",
    API_STARTING_MESSAGE,
    "应用正在启动，请稍候。",
    "运行状态连接失败。",
  ].includes(message ?? "")
}

async function waitForApiReady() {
  for (let attempt = 0; attempt < API_READY_ATTEMPTS; attempt += 1) {
    try {
      const health = await api.checkApiHealth()
      if (health.ok) {
        return true
      }
    } catch {
      await delay(API_READY_INTERVAL_MS)
    }
  }
  return false
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}
