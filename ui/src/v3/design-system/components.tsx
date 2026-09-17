/*
 * NovelForge V3 领域组件：ObjectiveCard / NextActionCard / StageTrack /
 * EntitySummaryCard / AlertCard / ContextPanel / NovelHero。
 *
 * 这些组件只接收 ViewModel（`ui/src/v3/viewmodel.ts` 的产物），不解析 StoryState、
 * 不判断 stage / objective 是否完成——判断全部来自 application 投影。
 */
import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import Icon, { STATUS_ICON, STATUS_LABEL } from './icons/IconRegistry'
import { Badge, Button, Card, CheckItem, ProgressBar } from './primitives'
import type {
  AlertViewModel, ChapterViewModel, CharacterEntityViewModel, ContentCardViewModel,
  EntityVisualViewModel, FactionEntityViewModel, HeroViewModel, LocationEntityViewModel,
  NextActionViewModel, ObjectiveViewModel, RecentItemViewModel, RouteCandidateViewModel,
  StageViewModel,
} from '../viewmodel'

/* ------------------------------------------------------------------- Hero */
export function NovelHero({ hero, onContinue }: {
  hero: HeroViewModel
  onContinue: () => void
}) {
  return (
    <Card className="v3-hero" tone="elevated" testId="v3-novel-hero">
      {/*
       * 作品视觉名片：Hero 默认美术作为背景层，文字与 CTA 永远在可读层之上
       * （scrim 只做可读性，不改图片文件本身）。
       */}
      <div className="v3-hero-visual" aria-hidden="true" data-testid="v3-hero-visual">
        <EntityVisual visual={hero.visual} size="fill" testId="v3-hero-artwork" />
        <span className="v3-hero-scrim" />
      </div>
      <div className="v3-hero-body">
        <h1 data-testid="v3-hero-title">{hero.title}</h1>
        {hero.tags.length > 0 && <div className="v3-hero-tags">
          {hero.tags.map((tag) => <span key={tag} className="v3-hero-tag">{tag}</span>)}
        </div>}
        {hero.premise && <p className="v3-hero-premise" data-testid="v3-hero-premise">{hero.premise}</p>}
        <div className="v3-hero-progress">
          <ProgressBar percent={hero.progressPercent} label={hero.progressLabel}
            testId="v3-hero-progress" />
        </div>
      </div>
      <div className="v3-hero-aside">
        <div className="v3-hero-stage" data-testid="v3-hero-stage">
          <span className="v3-hero-stage-label">当前阶段</span>
          <b>{hero.stageLabel}</b>
          <small>{hero.stageProgressLabel}</small>
        </div>
        <Button variant="primary" iconAfter="next_action" onClick={onContinue}
          testId="v3-hero-continue">{hero.continueLabel}</Button>
      </div>
    </Card>
  )
}

/* -------------------------------------------------------------- StageTrack */
export function StageTrack({ stages, onSelect, activeStageId }: {
  stages: StageViewModel[]
  onSelect?: (stageId: string) => void
  activeStageId?: string
}) {
  return (
    <ol className="v3-stage-track" data-testid="v3-stage-track">
      {stages.map((stage, index) => (
        <li key={stage.stageId}
          className={`v3-stage v3-stage-${stage.statusClass.toLowerCase()}`
            + (stage.current ? ' is-current' : '')
            + (activeStageId === stage.stageId ? ' is-active' : '')}>
          <button type="button" className="v3-stage-hit" onClick={() => onSelect?.(stage.stageId)}
            disabled={!stage.reachable}
            aria-current={stage.current ? 'step' : undefined}
            aria-label={`${stage.label}：${stage.statusLabel}`}
            data-testid={`v3-stage-${stage.stageId}`}
            data-status={stage.statusClass}>
            <span className="v3-stage-icon">
              <Icon name={STATUS_ICON[stage.statusClass] ?? stage.icon} size={24} />
            </span>
            <span className="v3-stage-label">{stage.label}</span>
            <span className="v3-stage-status">{stage.statusLabel}</span>
          </button>
          {index < stages.length - 1
            ? <span className={`v3-stage-link ${stage.statusClass === 'COMPLETE' ? 'is-done' : ''}`} aria-hidden="true" />
            : null}
        </li>
      ))}
    </ol>
  )
}

/* ----------------------------------------------------------- NextAction */
export function NextActionCard({ action, onRun, ctaVariant = 'primary' }: {
  action: NextActionViewModel
  onRun: (action: NextActionViewModel) => void
  /** 工作区已经有自己的唯一 Primary CTA 时，这里降级为 secondary。 */
  ctaVariant?: 'primary' | 'secondary'
}) {
  return (
    <Card className="v3-next-action" tone="elevated" testId="v3-next-action">
      <div className="v3-next-action-head">
        <span className="v3-next-action-icon"><Icon name={action.icon} size={22} /></span>
        <span className="v3-next-action-kicker" data-testid="v3-next-action-kicker">下一步</span>
        {action.blocking ? <Badge tone="danger" icon="warning">必须处理</Badge> : null}
      </div>
      <h2 data-testid="v3-next-action-title">{action.title}</h2>
      <p data-testid="v3-next-action-reason">{action.reason}</p>
      {action.impact ? <p className="v3-next-action-impact">
        <Icon name="next_action" size={14} />{action.impact}
      </p> : null}
      <Button variant={ctaVariant} iconAfter="next_action" onClick={() => onRun(action)}
        testId="v3-next-action-cta">{action.actionLabel}</Button>
    </Card>
  )
}

/* ---------------------------------------------------------- ObjectiveCard */
export function ObjectiveCard({ objective, onOpen, ctaVariant }: {
  objective: ObjectiveViewModel
  onOpen: (objective: ObjectiveViewModel) => void
  /** 未指定时按「是否推荐」决定；工作区需要唯一 Primary CTA 时显式降级。 */
  ctaVariant?: 'primary' | 'secondary'
}) {
  const shown = objective.checklist.slice(0, 5)
  return (
    <Card className="v3-objective" tone="default" testId="v3-objective-card"
      selected={objective.recommended}>
      <div className="v3-objective-head">
        <span className="v3-objective-icon"><Icon name={objective.icon} size={22} /></span>
        <h3>{objective.title}</h3>
        <span className="v3-objective-count" data-testid="v3-objective-count">
          {objective.progressLabel}
        </span>
      </div>
      <ProgressBar percent={objective.percent} showValue={false} compact />
      {shown.length > 0
        ? <ul className="v3-objective-checks" data-testid="v3-objective-checks">
          {shown.map((row) => (
            <CheckItem key={row.itemId} label={row.label} done={row.done}
              optional={row.optional} />
          ))}
        </ul>
        : <p className="v3-objective-hint">{objective.hint}</p>}
      {shown.length > 0 && objective.progress.total > shown.length
        ? <p className="v3-objective-hint">
          还有 {objective.progress.total - shown.length} 项
        </p>
        : null}
      <Button variant={ctaVariant ?? (objective.recommended ? 'primary' : 'secondary')}
        onClick={() => onOpen(objective)} testId="v3-objective-cta">
        {objective.actionLabel}
      </Button>
    </Card>
  )
}

/* ------------------------------------------------------ EntitySummaryCard */
export function EntitySummaryCard({ card, onOpen }: {
  card: ContentCardViewModel
  onOpen: (card: ContentCardViewModel) => void
}) {
  return (
    <Card as="li" className="v3-entity" tone="default" onClick={() => onOpen(card)}
      testId={`v3-content-${card.cardId}`}>
      <span className="v3-entity-visual" aria-hidden="true">
        <Icon name={card.icon} size={26} />
      </span>
      <span className="v3-entity-label">{card.label}</span>
      <span className="v3-entity-count" data-testid={`v3-content-count-${card.cardId}`}>
        {card.count} {card.unit}
      </span>
      <span className="v3-entity-hint">{card.hint}</span>
      <span className="v3-entity-more"><Icon name="next_action" size={16} /></span>
    </Card>
  )
}

/* -------------------------------------------------------------- AlertCard */
export function AlertCard({ alert, onOpen }: {
  alert: AlertViewModel
  onOpen?: (alert: AlertViewModel) => void
}) {
  const tone = alert.level === 'BLOCKING' ? 'danger'
    : alert.level === 'WARNING' ? 'warning' : 'neutral'
  return (
    <Card as="li" className={`v3-alert v3-alert-${alert.level.toLowerCase()}`}
      tone="quiet" testId={`v3-alert-${alert.alertId}`}>
      <Icon name={alert.level === 'INFO' ? 'foreshadow' : 'warning'} size={18} />
      <div className="v3-alert-body">
        <b>{alert.title}</b>
        {alert.detail ? <p>{alert.detail}</p> : null}
      </div>
      <Badge tone={tone}>{alert.levelLabel}</Badge>
      {onOpen ? <button type="button" className="v3-alert-action"
        onClick={() => onOpen(alert)}>{alert.actionLabel}</button> : null}
    </Card>
  )
}

/* ------------------------------------------------------------ ContextPanel */
/**
 * 目标 / 章节详情的上下文面板。
 *
 * 无障碍契约（与移动端抽屉一致的 Esc 行为，不引入新的 Dialog 库）：
 * role="dialog" + aria-modal + aria-labelledby，打开时焦点进入，
 * Tab 被限制在面板内，Esc 关闭，关闭后焦点返回原触发按钮。
 */
export function ContextPanel({ open, title, subtitle, onClose, children, footer }: {
  open: boolean
  title: string
  subtitle?: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const restoreRef = useRef<HTMLElement | null>(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  const titleId = useId()

  useEffect(() => {
    if (!open) return undefined
    const node = panelRef.current
    restoreRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement : null
    const focusables = (): HTMLElement[] => {
      if (!node) return []
      return Array.from(node.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'))
        .filter((element) => !element.hasAttribute('disabled'))
    }
    const items = focusables()
    ;(items[0] ?? node)?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const rows = focusables()
      if (rows.length === 0) return
      const first = rows[0]
      const last = rows[rows.length - 1]
      const active = document.activeElement
      const inside = Boolean(node && active && node.contains(active))
      if (event.shiftKey && (!inside || active === first)) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (!inside || active === last)) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      // 关闭后焦点返回原触发按钮，避免焦点掉回 <body>。
      const restore = restoreRef.current
      if (restore && document.contains(restore)) restore.focus()
    }
  }, [open])

  if (!open) return null
  return (
    <div className="v3-context" role="dialog" aria-modal="true" aria-labelledby={titleId}
      ref={panelRef} tabIndex={-1} data-testid="v3-context-panel">
      <header className="v3-context-head">
        <div>
          <h2 id={titleId} data-testid="v3-context-title">{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        <button type="button" className="v3-icon-btn v3-icon-btn-ghost"
          aria-label="关闭" onClick={onClose} data-testid="v3-context-close">
          <Icon name="close" size={18} />
        </button>
      </header>
      <div className="v3-context-body">{children}</div>
      {footer ? <footer className="v3-context-foot">{footer}</footer> : null}
    </div>
  )
}

/* ------------------------------------------------------------ EntityVisual */
/**
 * 统一实体视觉（P2 §7 Visual Asset Contract 的唯一实现入口）。
 *
 * 角色 / 地点 / 势力 / 章节 / 作品都必须通过这里渲染视觉区：
 * 有真实图片时显示图片，没有时用设计系统的统一 placeholder（同一套色调 + 语义图标），
 * 组件不得各自写渐变或随机占位。
 *
 * Broken asset fallback（V3 Visual Asset Gate §8）：
 * 图片请求失败时回到同一个语义图标占位——不允许出现 broken image icon、
 * 空白 Card 或布局塌陷；容器尺寸始终由 `size` 决定，因此不会有 CLS。
 */
export function EntityVisual({ visual, size = 'md', label, testId }: {
  visual: EntityVisualViewModel
  size?: 'sm' | 'md' | 'lg' | 'fill'
  label?: string
  testId?: string
}) {
  const iconSize = size === 'lg' ? 34 : size === 'sm' ? 18 : 26
  const [broken, setBroken] = useState(false)
  const [loaded, setLoaded] = useState(false)
  // 换了实体 / 换了图之后重新给一次机会，否则坏图状态会粘在下一条记录上。
  useEffect(() => { setBroken(false); setLoaded(false) }, [visual.imageUrl])
  const showImage = Boolean(visual.imageUrl) && !broken
  // 图标只在「图还没到」或「图坏了」时显示：图到了就必须让位，否则透明徽记会透出底层图标。
  const showIcon = !loaded || broken
  return (
    <span className={`v3-artwork v3-artwork-${size} v3-artwork-${visual.kind}`}
      data-testid={testId ?? 'v3-entity-visual'}
      data-artwork={showImage ? 'image' : 'placeholder'}
      data-artwork-source={visual.source}
      role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      {/*
       * 语义图标作为底层兜底：
       *   * 图片还在懒加载 / 解码时不会出现空白 Card；
       *   * 图片请求失败时立刻回到图标（无 CLS、无 broken image、无布局塌陷）。
       */}
      {showIcon ? <Icon name={visual.icon} size={iconSize} /> : null}
      {showImage ? (
        <img src={visual.imageUrl} alt="" loading="lazy" decoding="async"
          data-testid="v3-artwork-image"
          onLoad={() => setLoaded(true)}
          onError={() => setBroken(true)} />
      ) : null}
    </span>
  )
}

/* ----------------------------------------------------------- CharacterCard */
export function CharacterCard({ character, onOpen }: {
  character: CharacterEntityViewModel
  onOpen: (character: CharacterEntityViewModel) => void
}) {
  return (
    <Card as="li" className="v3-character" tone="default"
      onClick={() => onOpen(character)} testId={`v3-character-${character.characterId}`}>
      <EntityVisual visual={character.visual} size="lg"
        label={`${character.name} 的角色视觉`} testId="v3-character-visual" />
      <span className="v3-character-body">
        <span className="v3-character-head">
          <b>{character.name}</b>
          <Badge tone={character.isProtagonist ? 'primary' : 'neutral'}>
            {character.roleLabel}
          </Badge>
          {/* NF-016：设定候选给的是原型名；必须让作者知道它还是占位，而不是姓名。 */}
          {character.namePlaceholder ? (
            <Badge tone="warning" icon="warning">占位名</Badge>
          ) : null}
        </span>
        {character.statusLabel ? (
          <span className="v3-character-state">{character.statusLabel}</span>
        ) : null}
        {character.tags.length > 0 ? (
          <span className="v3-character-tags">
            {character.tags.map((tag) => <span key={tag}>{tag}</span>)}
          </span>
        ) : null}
        {character.factsLabel ? (
          <span className="v3-character-facts">{character.factsLabel}</span>
        ) : null}
        {/* 关系只显示真实可推导的摘要；详情在 ContextPanel。 */}
        <span className="v3-character-relations"
          data-testid="v3-character-relations">
          {character.hasRelationships
            ? `${character.relationshipCount} 条关系`
            : '尚未建立关键关系'}
        </span>
      </span>
      <span className="v3-character-go" aria-hidden="true">
        <Icon name="next_action" size={16} />
      </span>
    </Card>
  )
}

/* ------------------------------------------------------------ LocationCard */
export function LocationCard({ location, onOpen }: {
  location: LocationEntityViewModel
  onOpen: (location: LocationEntityViewModel) => void
}) {
  return (
    <Card as="li" className="v3-location" tone="default"
      onClick={() => onOpen(location)} testId={`v3-location-${location.locationId}`}>
      <EntityVisual visual={location.visual} size="lg"
        label={`${location.name} 的视觉`} testId="v3-location-visual" />
      <span className="v3-character-body">
        <span className="v3-character-head">
          <b>{location.name}</b>
          <Badge tone={location.current ? 'primary' : 'neutral'}>
            {location.current ? '当前地点' : location.kindLabel}
          </Badge>
          {location.namePlaceholder ? (
            <Badge tone="warning" icon="warning">占位名</Badge>
          ) : null}
        </span>
        {location.controlLabel ? (
          <span className="v3-character-state">控制方 {location.controlLabel}</span>
        ) : null}
        {location.factsLabel ? (
          <span className="v3-character-facts">{location.factsLabel}</span>
        ) : null}
      </span>
      <span className="v3-character-go" aria-hidden="true">
        <Icon name="next_action" size={16} />
      </span>
    </Card>
  )
}

/* ------------------------------------------------------------- FactionCard */
export function FactionCard({ faction, onOpen }: {
  faction: FactionEntityViewModel
  onOpen: (faction: FactionEntityViewModel) => void
}) {
  return (
    <Card as="li" className="v3-faction" tone="default"
      onClick={() => onOpen(faction)} testId={`v3-faction-${faction.factionId}`}>
      <EntityVisual visual={faction.visual} size="lg"
        label={`${faction.name} 的徽记`} testId="v3-faction-visual" />
      <span className="v3-character-body">
        <span className="v3-character-head">
          <b>{faction.name}</b>
          <Badge tone="neutral">势力</Badge>
          {faction.namePlaceholder ? (
            <Badge tone="warning" icon="warning">占位名</Badge>
          ) : null}
        </span>
        {faction.stanceLabel ? (
          <span className="v3-character-state">{faction.stanceLabel}</span>
        ) : null}
        <span className="v3-character-facts">{faction.factsLabel}</span>
      </span>
      <span className="v3-character-go" aria-hidden="true">
        <Icon name="next_action" size={16} />
      </span>
    </Card>
  )
}

/* ------------------------------------------------------- RouteCandidateCard */
/**
 * Route Visual Entity：把引擎候选行动表达成「故事可能性」。
 *
 * Primary UI 只出现作者读得懂的东西（方向 / 类型 / 是否可做 / 代价 / 影响对象）；
 * branch_id / runtime_id / raw score / weights 一律进 Advanced 或 legacy RouteLab。
 */
export function RouteCandidateCard({ candidate, selected = false, onOpen, onPick,
  compared = false, onCompare }: {
  candidate: RouteCandidateViewModel
  selected?: boolean
  onOpen: (candidate: RouteCandidateViewModel) => void
  onPick?: (candidate: RouteCandidateViewModel) => void
  compared?: boolean
  onCompare?: (candidate: RouteCandidateViewModel) => void
}) {
  return (
    <Card as="li" className="v3-route" tone="default" selected={selected}
      onClick={() => onOpen(candidate)} testId={`v3-route-${candidate.candidateId}`}>
      <EntityVisual visual={candidate.visual} size="lg"
        label={`${candidate.title} 的路线视觉`} testId="v3-route-visual" />
      <span className="v3-character-body">
        <span className="v3-character-head">
          <b>{candidate.title}</b>
          <Badge tone={candidate.available ? 'primary' : 'neutral'}>{candidate.kindLabel}</Badge>
        </span>
        {candidate.reason ? (
          <span className="v3-character-state">{candidate.reason}</span>
        ) : null}
        <span className="v3-character-facts">
          {[
            candidate.stateLabel,
            candidate.costs.length > 0 ? `代价：${candidate.costs.join('、')}` : '',
            candidate.relatedCharacters.length > 0
              ? `影响：${candidate.relatedCharacters.join('、')}` : '',
            candidate.affectedLocations.length > 0
              ? `地点：${candidate.affectedLocations.join('、')}` : '',
            candidate.affectedFactions.length > 0
              ? `势力：${candidate.affectedFactions.join('、')}` : '',
          ].filter(Boolean).join(' · ')}
        </span>
      </span>
      <span className="v3-route-pick">
        {onCompare ? (
          <button type="button" className="v3-btn v3-btn-ghost v3-btn-sm"
            onClick={(event) => { event.stopPropagation(); onCompare(candidate) }}
            aria-pressed={compared}
            data-testid={`v3-route-compare-${candidate.candidateId}`}>
            {compared ? '取消对比' : '对比'}
          </button>
        ) : null}
        {onPick ? (
          <button type="button" className="v3-btn v3-btn-secondary v3-btn-sm"
            onClick={(event) => { event.stopPropagation(); onPick(candidate) }}
            disabled={!candidate.available}
            data-testid={`v3-route-pick-${candidate.candidateId}`}>
            选这条
          </button>
        ) : null}
      </span>
    </Card>
  )
}

/* ------------------------------------------------------------- ChapterCard */
export function ChapterCard({ chapter, onOpen }: {
  chapter: ChapterViewModel
  onOpen: (chapter: ChapterViewModel) => void
}) {
  return (
  <Card as="li" className="v3-chapter" tone="default"
      onClick={() => onOpen(chapter)} testId={`v3-chapter-${chapter.chapterId}`}>
      {/* 章节不再只是纯文字 Card：视觉 + 序号同处一列，序号压在图上但不遮住画面主体。 */}
      <span className="v3-chapter-art">
        <EntityVisual visual={chapter.visual} size="fill"
          label={`${chapter.title} 的章节视觉`} testId="v3-chapter-visual" />
        <span className="v3-chapter-order" aria-hidden="true">
          {String(chapter.order).padStart(2, '0')}
        </span>
      </span>
      <span className="v3-chapter-body">
        <span className="v3-chapter-head">
          <b>{chapter.title}</b>
          <Badge tone={chapter.statusTone}>{chapter.statusLabel}</Badge>
        </span>
        {chapter.summary ? <span className="v3-chapter-summary">{chapter.summary}</span> : null}
        {[chapter.arcTitle, chapter.metaLabel].filter(Boolean).length > 0 ? (
          <span className="v3-chapter-meta">
            {[chapter.arcTitle, chapter.metaLabel].filter(Boolean).join(' · ')}
          </span>
        ) : null}
      </span>
      <span className="v3-chapter-go" aria-hidden="true">
        <Icon name="next_action" size={16} />
      </span>
    </Card>
  )
}

/* ---------------------------------------------------------- RecentItemCard */
export function RecentItemCard({ item, onOpen }: {
  item: RecentItemViewModel
  onOpen: (item: RecentItemViewModel) => void
}) {
  return (
    <Card as="li" className="v3-recent" tone="quiet"
      onClick={() => onOpen(item)} testId={`v3-recent-${item.itemId}`}>
      <span className="v3-recent-visual" aria-hidden="true"><Icon name={item.icon} size={20} /></span>
      <span className="v3-recent-label">{item.label}</span>
      <span className="v3-recent-detail">{item.detail}</span>
      <span className="v3-recent-time">{item.updatedLabel}</span>
    </Card>
  )
}

/* ---------------------------------------------------------------- RiskLink */
export function RiskSummary({ alerts, onOpen }: {
  alerts: AlertViewModel[]
  onOpen?: (alert: AlertViewModel) => void
}) {
  if (alerts.length === 0) return null
  const blocking = alerts.filter((row) => row.level === 'BLOCKING').length
  const warning = alerts.filter((row) => row.level === 'WARNING').length
  return (
    <div className="v3-risk-summary" data-testid="v3-risk-summary">
      <span><Icon name="warning" size={16} />
        {blocking > 0 ? `${blocking} 项需要处理` : warning > 0 ? `${warning} 项建议检查` : '提示'}
      </span>
      <ul>{alerts.slice(0, 3).map((row) => (
        <AlertCard key={row.alertId} alert={row} onOpen={onOpen} />
      ))}</ul>
    </div>
  )
}

export function StatusPill({ status }: { status: string }) {
  const tone = status === 'COMPLETE' ? 'success' : status === 'BLOCKED' ? 'danger'
    : status === 'CURRENT' ? 'primary' : status === 'AVAILABLE' ? 'neutral' : 'neutral'
  return <Badge tone={tone} icon={STATUS_ICON[status]}>
    {STATUS_LABEL[status] ?? status}
  </Badge>
}
