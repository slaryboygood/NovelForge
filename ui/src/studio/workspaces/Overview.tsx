/*
 * Studio Overview —— 作者打开作品第一眼看到的东西（§8、§12、§64）。
 *
 * 所有数字都来自 `/studio/overview`（backend 算好）；UI 不推导进度、不判断质量。
 */
import type { StudioOverview } from '../../api/studio'
import { Button, Card, ProgressBar } from '../../design-system/primitives'
import Icon from '../../design-system/icons/IconRegistry'
import { StatusBadge } from '../design/status'
import { nodeTypeLabel } from '../design/fields'

export function Overview({ data, onNavigate, onGenerate, generating }: {
  data: StudioOverview
  onNavigate: (view: string) => void
  onGenerate: (task: string) => void
  generating: string
}) {
  const { blueprint, quality, setup, payoff, delivery } = data
  const gateCells = quality.gates.filter((row) => row.gate !== 'Q4')
  const passed = gateCells.filter((row) => row.status === 'passed').length
  const next = data.next_action || {}

  return (
    <div className="studio-overview" data-testid="studio-overview">
      <section className="studio-hero">
        <div className="studio-hero-copy">
          <p className="studio-eyebrow">{data.genre || '故事蓝图'}</p>
          <h1>{data.title}</h1>
          <p className="studio-hero-sub">
            Story Blueprint：{blueprint.node_count} 个节点 ·
            已接受 {blueprint.accepted} · 待接受 {blueprint.proposed}
          </p>
          <div className="studio-hero-badges">
            <StatusBadge status={quality.status} testId="overview-quality-status" />
            <span className="studio-meta">
              {blueprint.selection_mode === 'accepted' ? '依据已接受版本' : '依据当前工作版本'}
            </span>
          </div>
        </div>
        <div className="studio-hero-actions">
          <Button variant="primary" icon="next_action"
            onClick={() => onNavigate(next.target_view || 'creation')}
            testId="overview-next-step">
            {next.action_label || '继续下一步'}
          </Button>
          <Button variant="secondary" icon="review"
            onClick={() => onNavigate('quality')}>去检查</Button>
        </div>
      </section>

      <div className="studio-grid studio-grid-3">
        <Card tone="elevated" testId="overview-structure">
          <header className="studio-tile-head">
            <Icon name="outline" size={20} /><h2>结构完成度</h2>
          </header>
          <ul className="studio-counts">
            {Object.entries(blueprint.by_type).map(([type, count]) => (
              <li key={type}>
                <span>{nodeTypeLabel(type)}</span><b>{count}</b>
              </li>
            ))}
            {blueprint.node_count === 0 ? (
              <li className="studio-muted">还没有结构内容</li>
            ) : null}
          </ul>
          <div className="studio-tile-actions">
            {blueprint.node_count === 0 ? (
              <Button variant="primary" icon="creation" onClick={() => onGenerate('premise')}
                disabled={Boolean(generating)} testId="overview-generate-premise">
                {generating === 'premise' ? '生成中…' : '生成故事前提'}
              </Button>
            ) : null}
            <Button variant="ghost" icon="story"
              onClick={() => onNavigate('story')}>查看故事结构</Button>
          </div>
        </Card>

        <Card tone="elevated" testId="overview-quality">
          <header className="studio-tile-head">
            <Icon name="review" size={20} /><h2>质量检查</h2>
            <StatusBadge status={quality.status} />
          </header>
          <ProgressBar percent={gateCells.length
            ? (passed / gateCells.length) * 100 : 0}
            label={`${passed}/${gateCells.length} 个门禁通过`} compact />
          <ul className="studio-gate-row">
            {gateCells.map((row) => (
              <li key={row.gate} title={row.skipped_reason || ''}>
                <span className={`studio-gate-dot is-${row.status}`} aria-hidden="true" />
                <span>{row.gate}</span>
                <span className="studio-meta">{row.issues > 0 ? `${row.issues}` : ''}</span>
              </li>
            ))}
          </ul>
          <p className="studio-muted">
            {quality.issues > 0 ? `${quality.issues} 个问题待处理` : '没有待处理的问题'}
            {quality.open_blockers > 0 ? `（${quality.open_blockers} 个门禁被阻止）` : ''}
          </p>
          <div className="studio-tile-actions">
            <Button variant="secondary" icon="review"
              onClick={() => onNavigate('quality')}>打开检查中心</Button>
          </div>
        </Card>

        <Card tone="elevated" testId="overview-delivery">
          <header className="studio-tile-head">
            <Icon name="export" size={20} /><h2>交付</h2>
          </header>
          <p className="studio-muted">
            {delivery.snapshots > 0
              ? `已经交付过 ${delivery.snapshots} 次`
              : '还没有交付记录'}
          </p>
          {delivery.last ? (
            <p className="studio-meta">
              最近：{String(delivery.last.snapshot_id)}
              {delivery.last.formats?.length
                ? ` · ${delivery.last.formats.join(' / ')}` : ''}
            </p>
          ) : null}
          <div className="studio-tile-actions">
            <Button variant="secondary" icon="export"
              onClick={() => onNavigate('delivery')}>准备交付</Button>
          </div>
        </Card>
      </div>

      <div className="studio-grid studio-grid-2">
        <Card tone="elevated" testId="overview-setup">
          <header className="studio-tile-head">
            <Icon name="foreshadow" size={20} /><h2>伏笔与回收</h2>
          </header>
          <ul className="studio-counts">
            <li><span>未回收</span><b>{setup.counts.open ?? 0}</b></li>
            <li><span>部分回收</span><b>{setup.counts.partially_paid ?? 0}</b></li>
            <li><span>已回收</span><b>{setup.counts.paid ?? 0}</b></li>
            <li><span>已放弃</span><b>{setup.counts.abandoned ?? 0}</b></li>
          </ul>
          {setup.unpaid_required > 0 ? (
            <p className="studio-warning-line" data-testid="overview-unpaid-setup">
              <Icon name="warning" size={16} />
              还有 {setup.unpaid_required} 条伏笔没有回收，交付前需要处理。
            </p>
          ) : (
            <p className="studio-muted">所有伏笔都有去处。</p>
          )}
          <div className="studio-tile-actions">
            <Button variant="ghost" icon="foreshadow"
              onClick={() => onNavigate('scenes')}>查看伏笔分布</Button>
          </div>
        </Card>

        <Card tone="elevated" testId="overview-next">
          <header className="studio-tile-head">
            <Icon name="next_action" size={20} /><h2>推荐下一步</h2>
          </header>
          <p className="studio-next-title">{next.title || '继续完善故事结构'}</p>
          <p className="studio-muted">{next.reason || '根据当前进度，继续推进结构。'}</p>
          {next.impact ? <p className="studio-meta">{next.impact}</p> : null}
          <div className="studio-tile-actions">
            <Button variant="primary" icon="next_action"
              onClick={() => onNavigate(next.target_view || 'creation')}>
              {next.action_label || '开始'}
            </Button>
          </div>
        </Card>
      </div>

      {payoff.counts && Object.keys(payoff.counts).length > 0 ? (
        <p className="studio-meta" data-testid="overview-payoff">
          回收记录：{Object.entries(payoff.counts)
            .map(([key, value]) => `${key} ${value}`).join(' · ')}
        </p>
      ) : null}
    </div>
  )
}
