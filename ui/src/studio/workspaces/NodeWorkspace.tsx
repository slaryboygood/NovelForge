/*
 * 通用节点工作区（创造 / 世界 / 故事 / 场景 / 人物共用一套卡片网格）。
 *
 * 不做任何业务判断：读 `/studio/blueprint`，显示卡片，点击进入编辑器抽屉；
 * 生成动作经 `/studio/generate`（结果一定是 proposal，等待作者接受，§34）。
 */
import { useMemo, useState } from 'react'
import type { StudioNode } from '../../api/studio'
import { Button, Card, SectionHeading } from '../../design-system/primitives'
import Icon from '../../design-system/icons/IconRegistry'
import { StatusBadge } from '../design/status'
import { NodeCard } from '../components'
import { nodeTypeLabel } from '../design/fields'

export interface NodeWorkspaceProps {
  title: string
  icon: string
  hint: string
  nodes: StudioNode[]
  nodeTypes: string[]
  /** 生成动作（task id → 文案）；为空表示这一页还没有对应生成器。 */
  generateActions?: { task: string; label: string; needsParent?: boolean }[]
  generating?: string
  onGenerate?: (task: string) => void
  onOpen: (nodeId: string) => void
  /** 按章节分组（场景页）；给出 true 时用 parent_id 分组并显示章节标题。 */
  groupByParent?: boolean
  emptyReason?: string
  testId?: string
}

export function NodeWorkspace({
  title, icon, hint, nodes, nodeTypes, generateActions = [], generating = '',
  onGenerate, onOpen, groupByParent = false, emptyReason, testId,
}: NodeWorkspaceProps) {
  const [typeFilter, setTypeFilter] = useState('')
  const visible = useMemo(
    () => (typeFilter ? nodes.filter((row) => row.node_type === typeFilter) : nodes),
    [nodes, typeFilter])

  const groups = useMemo(() => {
    if (!groupByParent) return [['', visible]] as [string, StudioNode[]][]
    const buckets = new Map<string, StudioNode[]>()
    for (const node of visible) {
      const key = String(node.parent_id || '')
      buckets.set(key, [...(buckets.get(key) ?? []), node])
    }
    return [...buckets.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [visible, groupByParent])

  const titleOf = (nodeId: string) => {
    const node = nodes.find((row) => row.node_id === nodeId)
    return node ? String(node.visible?.title ?? node.payload?.title ?? nodeId) : nodeId
  }

  return (
    <section className="studio-workspace" data-testid={testId ?? `workspace-${icon}`}>
      <SectionHeading icon={icon} title={title} hint={hint}
        action={(
          <div className="studio-head-actions">
            {nodeTypes.length > 1 ? (
              <div className="studio-chip-row" role="group" aria-label="按类型筛选">
                <button type="button" className={`studio-chip ${typeFilter === '' ? 'is-active' : ''}`}
                  aria-pressed={typeFilter === ''} onClick={() => setTypeFilter('')}>全部</button>
                {nodeTypes.map((type) => (
                  <button key={type} type="button"
                    className={`studio-chip ${typeFilter === type ? 'is-active' : ''}`}
                    aria-pressed={typeFilter === type}
                    onClick={() => setTypeFilter(type)}>
                    {nodeTypeLabel(type)}
                  </button>
                ))}
              </div>
            ) : null}
            {generateActions.map((action) => (
              <Button key={action.task} variant="primary" icon="creation"
                disabled={Boolean(generating)}
                onClick={() => onGenerate?.(action.task)}
                testId={`generate-${action.task}`}>
                {generating === action.task ? '生成中…' : action.label}
              </Button>
            ))}
          </div>
        )} />

      {visible.length === 0 ? (
        <Card tone="quiet" className="studio-empty-card">
          <div className="studio-empty">
            <span className="studio-empty-icon"><Icon name={icon} size={26} /></span>
            <h3>还没有{title}</h3>
            <p>{emptyReason || '先创建或生成一条内容，这里就会出现卡片。'}</p>
            {generateActions.length > 0 ? (
              <Button variant="primary" icon="creation" disabled={Boolean(generating)}
                onClick={() => onGenerate?.(generateActions[0].task)}>
                {generateActions[0].label}
              </Button>
            ) : null}
          </div>
        </Card>
      ) : (
        groups.map(([parentId, rows]) => (
          <div key={parentId || 'all'} className="studio-group">
            {groupByParent && parentId ? (
              <h3 className="studio-group-title">
                <Icon name="chapter" size={18} />
                {titleOf(parentId)}
                <span className="studio-meta">{rows.length} 场</span>
              </h3>
            ) : null}
            <div className="studio-card-grid">
              {rows.map((node) => (
                <NodeCard key={node.node_id} node={node}
                  onOpen={() => onOpen(node.node_id)}
                  badgeStatus={String(node.status)} />
              ))}
            </div>
          </div>
        ))
      )}

      {visible.length > 0 ? (
        <p className="studio-meta studio-count-line">
          共 {visible.length} 条
          {visible.some((row) => row.status === 'proposed')
            ? ` · ${visible.filter((row) => row.status === 'proposed').length} 条待接受` : ''}
          {' '}<StatusBadge status="proposed" />
        </p>
      ) : null}
    </section>
  )
}
