import { useEffect } from 'react'
import StudioApp from './studio/StudioApp'
import './design-system/tokens.css'
import './design-system/primitives.css'
import './studio/studio.css'

/**
 * NovelForge V4 只有 **Story Studio** 一个产品面（`docs/v4/V4_UI_CONTRACT.md`）。
 *
 * V2 / V3 产品面已在 post-release cleanup 中移除，旧 URL 不再加载旧 bundle：
 *
 *   * `?ui=v3` / `#/v3...`             → 回落（fallback）到 Story Studio；
 *   * `?ui=v2` / `#/story-builder...`  → 回落（fallback）到 Story Studio。
 *
 * 旧入口只做一次 `replaceState` 归一化（不重新加载、不产生重定向循环），
 * 既保留旧书签可用性，又不再维护第二套产品 UI。
 */
const LEGACY_HASH_PREFIXES = ['#/v3', '#/story-builder']

export default function App() {
  useEffect(() => {
    try {
      const url = new URL(window.location.href)
      const surface = url.searchParams.get('ui')
      const hash = url.hash || ''
      const isLegacySurface = surface === 'v2' || surface === 'v3'
      const isLegacyHash = LEGACY_HASH_PREFIXES.some((prefix) =>
        hash.startsWith(prefix))
      if (isLegacySurface || isLegacyHash) {
        url.searchParams.delete('ui')
        url.hash = '#/'
        window.history.replaceState(null, '', url.toString())
        return
      }
      if (!hash) {
        url.hash = '#/'
        window.history.replaceState(null, '', url.toString())
      }
    } catch {
      // 非浏览器环境（单元测试）忽略 URL 归一化。
    }
  }, [])

  return <StudioApp />
}
