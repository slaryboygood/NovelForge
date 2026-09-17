import { useCallback, useEffect, useState } from 'react'

/**
 * M14：统一的只读资源加载（loading / error / reload），避免每个面板各写一套。
 *
 * - 只在 novelId 变化时自动加载；
 * - reload 由调用方按需触发（例如刷新按钮、上下文变化）。
 */
export function useApiData<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const reload = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setData(await loader())
    } catch (reason) {
      setData(null)
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => { void reload() }, [reload])
  return { data, loading, error, reload }
}

export function PanelState({ loading, error, empty, emptyText }: {
  loading: boolean; error: string; empty: boolean; emptyText: string
}) {
  if (loading) return <p className="world-empty" data-testid="panel-loading">正在读取…</p>
  if (error) return <div role="alert" className="story-builder-message error"
    data-testid="panel-error">{error}</div>
  if (empty) return <p className="world-empty" data-testid="panel-empty">{emptyText}</p>
  return null
}
