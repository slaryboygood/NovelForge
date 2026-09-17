import { useEffect, useState } from 'react'
import StoryBuilderPage from './StoryBuilderPage'
import V3App from './v3/V3App'
import './v3/design-system/tokens.css'
import './v3/v3.css'

/**
 * Product V3 是默认产品入口（Novel Landing → Novel Command Center）。
 *
 * V2 UI 完整保留并可从两处进入：
 *   * `#/story-builder?...`（V3 的「高级工具」入口，同一个应用内跳转）；
 *   * `?ui=v2`（旧入口 / 旧验收脚本 / 书签）。
 * 两者共用同一份 domain 与同一批 API，V2 不允许出现第二套业务规则。
 */
function isLegacyEntry(): boolean {
  try {
    const search = window.location.search || ''
    if (new URLSearchParams(search).get('ui') === 'v2') return true
    return (window.location.hash || '').startsWith('#/story-builder')
  } catch {
    return false
  }
}

export default function App() {
  const [legacy, setLegacy] = useState(() => isLegacyEntry())

  useEffect(() => {
    const normalize = () => {
      if (isLegacyEntry()) {
        setLegacy(true)
        return
      }
      setLegacy(false)
      // W6-05：深链接上下文（novel_id / tab / branch_id / package_id / step / group）
      // 挂在 hash query 上；路由归一化只处理 path 部分，不能丢掉这些参数。
      const hash = window.location.hash || ''
      const queryIndex = hash.indexOf('?')
      const path = queryIndex === -1 ? hash : hash.slice(0, queryIndex)
      const query = queryIndex === -1 ? '' : hash.slice(queryIndex)
      if (!path) {
        window.history.replaceState(null, '', '#/' + query)
      }
    }
    normalize()
    window.addEventListener('hashchange', normalize)
    return () => window.removeEventListener('hashchange', normalize)
  }, [])

  if (!legacy) return <div className="v3-root"><V3App /></div>

  return <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh' }}>
    <header style={{ padding: '16px 24px', borderBottom: '1px solid var(--border)' }}>
      <strong>NovelForge</strong><span style={{ marginLeft: 16, color: 'var(--muted)' }}>故事构筑</span>
      <a href="#/" style={{ marginLeft: 16, color: 'var(--accent, #e2b451)' }}
        data-testid="legacy-back-to-v3">返回新版工作台</a>
    </header>
    <StoryBuilderPage />
  </div>
}
