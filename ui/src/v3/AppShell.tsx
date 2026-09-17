/*
 * NovelForge V3 AppShell：左侧一级导航 + 中间主工作区 + 右侧辅助栏。
 *
 * 视觉优先级：Main Workspace > Current Objective > Next Action > Navigation > System Info。
 * 右侧栏只承载 Next Action / 当前目标 / 风险，没有内容时直接隐藏整块。
 */
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import Icon, { STATUS_ICON } from './design-system/icons/IconRegistry'
import { IconButton, ProgressBar } from './design-system/primitives'
import type { StageViewModel } from './viewmodel'
import { PRIMARY_NAV, type V3View } from './navModel'

export interface AppShellProps {
  novelTitle: string
  stageLabel: string
  stageProgressLabel: string
  progressPercent: number
  stages: StageViewModel[]
  activeView: V3View
  onNavigate: (view: V3View) => void
  onHome: () => void
  rail: ReactNode
  children: ReactNode
  alertCount: number
  onOpenAlerts: () => void
  onOpenLegacy: () => void
  onSwitchNovel: () => void
}

export default function AppShell({
  novelTitle, stageLabel, stageProgressLabel, progressPercent, stages, activeView,
  onNavigate, onHome, rail, children, alertCount, onOpenAlerts, onOpenLegacy,
  onSwitchNovel,
}: AppShellProps) {
  const [railOpen, setRailOpen] = useState(false)

  useEffect(() => { setRailOpen(false) }, [activeView])

  /** 抽屉打开时：Esc 关闭（无障碍要求），点击遮罩也关闭。 */
  useEffect(() => {
    if (!railOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setRailOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [railOpen])

  const navStatus = (stageId: string) => {
    if (!stageId) return ''
    return stages.find((row) => row.stageId === stageId)?.statusClass ?? ''
  }

  return (
    <div className="v3-shell" data-testid="v3-app-shell">
      <nav className="v3-nav" aria-label="主导航">
        <button type="button" className="v3-nav-brand" onClick={onHome}
          title="回到作品总览" data-testid="v3-nav-brand">
          <span className="v3-nav-mark" aria-hidden="true">
            <Icon name="book" size={20} />
          </span>
          <span className="v3-nav-brand-text">
            <b>NovelForge</b>
            <small>小说创作工作台</small>
          </span>
        </button>
        <ul className="v3-nav-list">
          {PRIMARY_NAV.map((item) => {
            const status = navStatus(item.stageId)
            const active = activeView === item.view
            return (
              <li key={item.view}>
                <button type="button"
                  className={`v3-nav-item ${active ? 'is-active' : ''}`
                    + (status ? ` status-${status.toLowerCase()}` : '')}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => onNavigate(item.view)}
                  data-testid={`v3-nav-${item.view}`}>
                  <span className="v3-nav-icon"><Icon name={item.icon} size={22} /></span>
                  <span className="v3-nav-label">{item.label}</span>
                  {status && status !== 'LOCKED' ? <span className="v3-nav-status" aria-hidden="true">
                    <Icon name={STATUS_ICON[status] ?? 'current'} size={13} />
                  </span> : null}
                  {status === 'LOCKED' ? <span className="v3-nav-lock" aria-hidden="true">
                    <Icon name="locked" size={13} />
                  </span> : null}
                </button>
              </li>
            )
          })}
        </ul>
        <div className="v3-nav-foot">
          <button type="button" className="v3-nav-item" onClick={onOpenLegacy}
            data-testid="v3-nav-legacy">
            <span className="v3-nav-icon"><Icon name="repair" size={22} /></span>
            <span className="v3-nav-label">高级工具</span>
          </button>
          <button type="button" className="v3-nav-item" onClick={onSwitchNovel}
            data-testid="v3-nav-switch-novel">
            <span className="v3-nav-icon"><Icon name="more" size={22} /></span>
            <span className="v3-nav-label">切换作品</span>
          </button>
        </div>
      </nav>

      <div className="v3-main-area">
        <header className="v3-topbar">
          <div className="v3-topbar-left">
            {/* 行为是「回到当前作品总览」，因此文案与 aria-label 必须与之一致；
                真正回作品列表由左下角「切换作品」承担。 */}
            <IconButton icon="home" label="回到作品总览" onClick={onHome} testId="v3-top-home" />
            <div className="v3-topbar-title">
              <b data-testid="v3-topbar-title">{novelTitle}</b>
              <span className="v3-topbar-stage" data-testid="v3-topbar-stage">{stageLabel}</span>
            </div>
          </div>
          <div className="v3-topbar-right">
            <div className="v3-topbar-progress">
              <ProgressBar percent={progressPercent} showValue={false} compact
                label={`总体进度 ${progressPercent}%`} />
              <small data-testid="v3-topbar-progress">{progressPercent}% · {stageProgressLabel}</small>
            </div>
            {/* 它不是通知中心：打开的是「需要留意的问题 / 检查」。 */}
            <IconButton icon={alertCount > 0 ? 'warning' : 'review'}
              label={alertCount > 0 ? `需要留意的问题（${alertCount}）` : '打开检查'}
              count={alertCount} onClick={onOpenAlerts} testId="v3-top-alerts" />
            <button type="button" className="v3-rail-toggle" onClick={() => setRailOpen((v) => !v)}
              aria-expanded={railOpen} data-testid="v3-rail-toggle">
              <Icon name="objective" size={18} />
              <span>目标</span>
            </button>
          </div>
        </header>
        <div className="v3-body">
          <main className="v3-workspace" data-testid="v3-workspace">{children}</main>
          {railOpen ? (
            <div className="v3-rail-backdrop" role="presentation"
              onClick={() => setRailOpen(false)} data-testid="v3-rail-backdrop" />
          ) : null}
          <aside className={`v3-rail ${railOpen ? 'is-open' : ''}`} aria-label="当前目标与下一步"
            data-testid="v3-rail">
            <button type="button" className="v3-rail-close" onClick={() => setRailOpen(false)}
              aria-label="收起目标面板" data-testid="v3-rail-close">
              <Icon name="close" size={18} />
            </button>
            {rail}
          </aside>
        </div>
      </div>
    </div>
  )
}
