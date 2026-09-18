/*
 * NovelForge V4 共享 HTTP 入口。
 *
 * post-release cleanup 之前，这一层位于 `ui/src/api.ts`（V2 面板客户端）。
 * V2 面板已删除，只保留 Story Studio 真正使用的 JSON 请求语义：
 *
 *   · 唯一 fetch 入口（feature 组件不得直接 fetch，见 `docs/v4/V4_UI_CONTRACT.md` §11）；
 *   · 错误统一为 `ApiError`（status + detail）→ 由 `studio/design/errors.ts` 映射成作者语言；
 *   · 与旧实现保持同一错误语义（后端 `detail` 原样保留），不改变任何 wire 行为。
 */

const BASE = ''

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function messageFromDetail(detail: unknown, body: string, fallback: string): string {
  if (typeof detail === 'string' && detail) return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const value = (detail as { message?: unknown }).message
    if (typeof value === 'string' && value) return value
  }
  return body || fallback
}

export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + url, init)
  if (!res.ok) {
    const body = await res.text()
    let payload: unknown = null
    try {
      payload = JSON.parse(body)
    } catch {
      // 保留非 JSON 错误体（原实现同语义）
    }
    const record = payload as { detail?: unknown } | null
    const detail = record?.detail ?? payload
    throw new ApiError(messageFromDetail(detail, body, res.statusText), res.status, detail)
  }
  return res.json() as Promise<T>
}

/** 交付物下载 URL（浏览器直链，不经 fetch）。 */
export function apiUrl(path: string): string {
  return BASE + path
}
