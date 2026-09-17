/*
 * Novel Command Center —— 进入作品后的默认工作区。
 *
 * 视觉主体是「小说本身」：Hero（作品身份 + 阶段 + 总体进度）→ 作者旅程 →
 * 当前阶段最有价值的核心对象 → 最近编辑。不是 KPI 仪表盘。
 */
import Icon from './design-system/icons/IconRegistry'
import {
  Card, EmptyState, ProgressBar, SectionHeading,
} from './design-system/primitives'
import { EntitySummaryCard, NovelHero, RecentItemCard, StageTrack } from './design-system/components'
import type { CommandCenterViewModel, ContentCardViewModel, RecentItemViewModel,
  StageViewModel } from './viewmodel'

export default function CommandCenter({ model, onContinue, onOpenView, onOpenContent,
  onOpenRecent }: {
  model: CommandCenterViewModel
  onContinue: () => void
  onOpenView: (view: string) => void
  onOpenContent: (card: ContentCardViewModel) => void
  onOpenRecent: (item: RecentItemViewModel) => void
}) {
  const currentStage = model.stages.find((row) => row.current) ?? null
  return (
    <div className="v3-command-center" data-testid="v3-command-center">
      <NovelHero hero={model.hero} onContinue={onContinue} />

      <Card className="v3-journey" tone="default" testId="v3-journey-card">
        <SectionHeading icon="progress" title="作者旅程"
          hint={model.currentObjective
            ? `当前阶段要做的：${model.currentObjective.title}`
            : `当前阶段：${model.hero.stageLabel}`}
          action={<span className="v3-journey-count" data-testid="v3-journey-count">
            {model.stages.filter((row) => row.statusClass === 'COMPLETE').length}
            {' / '}{model.stages.length} 阶段完成
          </span>} />
        <StageTrack stages={model.stages} onSelect={onOpenView}
          activeStageId={model.currentStageId} />
        {currentStage ? <p className="v3-journey-goal" data-testid="v3-stage-goal">
          <Icon name={currentStage.icon} size={16} />
          {currentStage.label}：{currentStage.goal}
        </p> : null}
      </Card>

      <section className="v3-block" data-testid="v3-core-content">
        <SectionHeading icon="objective" title="核心内容"
          hint="当前阶段最重要的对象" />
        {model.content.length > 0 ? (
          <ul className="v3-entity-grid">
            {model.content.map((card) => (
              <EntitySummaryCard key={card.cardId} card={card} onOpen={onOpenContent} />
            ))}
          </ul>
        ) : (
          <EmptyState icon="world" title="还没有内容"
            reason="世界、角色与剧情会在创作流程里一步步建立。"
            value="先写下一句话创意，系统会给出可选的设定方向。" />
        )}
      </section>

      {model.recent.length > 0 && (
        <section className="v3-block" data-testid="v3-recent-block">
          <SectionHeading icon="chapter" title="最近编辑"
            hint="作品里最近发生的改变" />
          <ul className="v3-recent-grid">
            {model.recent.map((item) => (
              <RecentItemCard key={item.itemId} item={item} onOpen={onOpenRecent} />
            ))}
          </ul>
        </section>
      )}

      <Card className="v3-milestones" tone="quiet" testId="v3-milestones">
        <SectionHeading icon="complete" title="当前成果" />
        <div className="v3-milestone-grid">
          {model.content.map((card) => (
            <div className="v3-milestone" key={card.cardId}>
              <Icon name={card.icon} size={20} />
              <b>{card.count}</b>
              <span>{card.unit}</span>
            </div>
          ))}
        </div>
      </Card>

      <div className="v3-progress-foot" data-testid="v3-command-progress">
        <ProgressBar percent={model.hero.progressPercent} label={model.hero.progressLabel} />
      </div>
    </div>
  )
}

export function JourneyRail({ model, onRun, onOpenObjective, onOpenAlert,
  ctaVariant = 'primary' }: {
  model: CommandCenterViewModel
  onRun: () => void
  onOpenObjective: () => void
  onOpenAlert: () => void
  /**
   * 工作区已经有自己的唯一 Primary CTA 时，右栏的 Next Action 降级为 secondary，
   * 避免同一个动作在同一屏出现两个同权重金色按钮。
   */
  ctaVariant?: 'primary' | 'secondary'
}) {
  const objective = model.currentObjective
  const alerts = model.alerts
  return (
    <div className="v3-rail-inner">
      <Card className="v3-next-action-card" tone="elevated" testId="v3-next-action">
        <div className="v3-next-action-head">
          <span className="v3-next-action-icon"><Icon name={model.nextAction.icon} size={22} /></span>
          <span className="v3-next-action-kicker">下一步</span>
          {model.nextAction.blocking
            ? <span className="v3-badge v3-badge-danger"><Icon name="warning" size={14} />必须处理</span>
            : null}
        </div>
        <h2 data-testid="v3-next-action-title">{model.nextAction.title}</h2>
        <p data-testid="v3-next-action-reason">{model.nextAction.reason}</p>
        {model.nextAction.impact
          ? <p className="v3-next-action-impact">
            <Icon name="next_action" size={14} />{model.nextAction.impact}
          </p>
          : null}
        <button type="button" className={`v3-btn v3-btn-${ctaVariant} v3-btn-md`}
          onClick={onRun} data-testid="v3-next-action-cta">
          <span className="v3-btn-label">{model.nextAction.actionLabel}</span>
          <Icon name="next_action" size={18} />
        </button>
      </Card>

      {objective ? (
        <Card className="v3-rail-objective" tone="default" testId="v3-current-objective">
          <div className="v3-next-action-head">
            <span className="v3-next-action-icon"><Icon name={objective.icon} size={22} /></span>
            <span className="v3-next-action-kicker">当前目标</span>
            <span className="v3-objective-count" data-testid="v3-current-objective-count">
              {objective.progressLabel}
            </span>
          </div>
          <h2 data-testid="v3-current-objective-title">{objective.title}</h2>
          <ProgressBar percent={objective.percent} showValue={false} compact />
          <ul className="v3-objective-checks" data-testid="v3-current-objective-checks">
            {objective.checklist.slice(0, 5).map((row) => (
              <li key={row.itemId} className={`v3-check ${row.done ? 'is-done' : ''}`}>
                <span className="v3-check-mark" aria-hidden="true">
                  {row.done ? <Icon name="complete" size={16} /> : <span className="v3-check-empty" />}
                </span>
                <span className="v3-check-label">{row.label}</span>
                <span className="v3-sr-only">{row.done ? '已完成' : '未完成'}</span>
              </li>
            ))}
          </ul>
          {objective.checklist.length === 0
            ? <p className="v3-objective-hint">{objective.why}</p> : null}
          <p className="v3-objective-unlock" data-testid="v3-current-objective-unlock">
            <Icon name="next_action" size={14} />{objective.unlockEffects}
          </p>
          <button type="button" className="v3-btn v3-btn-secondary v3-btn-md"
            onClick={onOpenObjective} data-testid="v3-current-objective-cta">
            <span className="v3-btn-label">{objective.actionLabel}</span>
          </button>
        </Card>
      ) : null}

      {alerts.length > 0 ? (
        <Card className="v3-rail-alerts" tone="quiet" testId="v3-risk-block">
          <div className="v3-next-action-head">
            <span className="v3-next-action-icon"><Icon name="warning" size={20} /></span>
            <span className="v3-next-action-kicker">需要留意</span>
          </div>
          <ul className="v3-alert-list">
            {alerts.slice(0, 3).map((alert) => (
              <li key={alert.alertId} className={`v3-alert v3-alert-${alert.level.toLowerCase()}`}
                data-testid={`v3-alert-${alert.alertId}`}>
                <Icon name={alert.level === 'INFO' ? 'foreshadow' : 'warning'} size={18} />
                <div className="v3-alert-body">
                  <b>{alert.title}</b>
                  {alert.detail ? <p>{alert.detail}</p> : null}
                </div>
                <span className={`v3-badge v3-badge-${alert.level === 'BLOCKING' ? 'danger'
                  : alert.level === 'WARNING' ? 'warning' : 'neutral'}`}>{alert.levelLabel}</span>
                <button type="button" className="v3-alert-action" onClick={onOpenAlert}
                  data-testid={`v3-alert-action-${alert.alertId}`}>{alert.actionLabel}</button>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  )
}
