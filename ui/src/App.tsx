import { useEffect, useState } from 'react'
import StoryBuilderPage from './StoryBuilderPage'
import V3App from './v3/V3App'
import StudioApp from './studio/StudioApp'
import './v3/design-system/tokens.css'
import './v3/v3.css'

/**
 * Product V4 的默认入口是 **Story Studio**（`ui/src/studio/**`）。
 *
 * 三个产品面并存，各自有明确的进入方式（`docs/v4/V4_UI_CONTRACT.md` §3）：
 *
 *   * `#/studio/...`（默认）→ V4 Story Studio（Blueprint 主产品路径）；
 *   * `?ui=v3` / `#/v3...`  → V3 工作台（兼容入口，旧验收脚本使用）；
 *   * `?ui=v2` / `#/story-builder?...` → V2 legacy 面板（高级工具）。
 *
 * 三者共用同一份 domain 与同一批 REST API：不允许出现第二套业务规则。
 */
type Surface = 'studio' | 'v3' | 'legacy'

function detectSurface(): Surface {
  try {
    const ui = new URLSearchParams(window.location.search || '').get('ui')
    if (ui === 'v2') return 'legacy'
    if (ui === 'v3') return 'v3'
    const hash = window.location.hash || ''
    if (hash.startsWith('#/story-builder')) return 'legacy'
    if (hash.startsWith('#/v3')) return 'v3'
    return 'studio'
  } catch {
    return 'studio'
  }
}

export default function App() {
  const [surface, setSurface] = useState<Surface>(() => detectSurface())

  useEffect(() => {
    const normalize = () => {
      setSurface(detectSurface())
      // 深链接上下文（novel_id / view / entity）挂在 hash 上；只补齐缺失的 path，
      // 不丢 query。
      const hash = window.location.hash || ''
      if (!hash) {
        window.history.replaceState(null, '', '#/')
      }
    }
    normalize()
    window.addEventListener('hashchange', normalize)
    return () => window.removeEventListener('hashchange', normalize)
  }, [])

  if (surface === 'studio') return <StudioApp />

  if (surface === 'v3') {
    return <div className="v3-root"><V3App /></div>
  }

  return <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh' }}>
    <header style={{ padding: '16px 24px', borderBottom: '1px solid var(--border)' }}>
      <strong>NovelForge</strong>
      <span style={{ marginLeft: 16, color: 'var(--muted)' }}>故事构筑（高级工具）</span>
      <a href="#/studio" style={{ marginLeft: 16, color: 'var(--accent, #e2b451)' }}
        data-testid="legacy-back-to-studio">返回 Story Studio</a>
    </header>
    <StoryBuilderPage />
  </div>
}
