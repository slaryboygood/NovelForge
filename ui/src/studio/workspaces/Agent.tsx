/*
 * Agent 工作区（V4-11 §65–§70、§103）：Goal → Plan → Steps → Approval → Result。
 *
 * 不是聊天框：自然语言只用于 goal input；计划 / 审批 / 结果全部结构化展示。
 * UI 不做任何编排判断（不猜哪一步会改什么、不推断能否交付）。
 */
import { useState } from 'react'
import {
  agentApi, type AgentPlanPreviewDto, type AgentResultDto, type AgentStatusDto,
} from '../../api/agent'
import { studioApi } from '../../api/studio'
import { useEffect } from 'react'
import { Button, Card, Disclosure, SectionHeading } from '../../design-system/primitives'
import Icon from '../../design-system/icons/IconRegistry'
import { StatusBadge } from '../design/status'
import { mapError } from '../design/errors'

const ACTION_LABELS: Record<string, string> = {
  inspect_blueprint: '查看当前状态',
  generate_node: '生成内容',
  regenerate_node: '重新生成',
  patch_node: '修改字段',
  rewrite_node: 'AI 改写',
  evaluate: '运行质量检查',
  plan_repair: '制定修复计划',
  repair: '执行修复',
  verify_repair: '复核修复',
  request_accept: '请求接受',
  accept_revision: '接受版本',
  validate_delivery: '交付预检',
  deliver: '正式交付',
}

const STEP_TONE: Record<string, string> = {
  completed: 'passed',
  skipped: 'draft',
  failed: 'failed',
  stale: 'blocked',
  awaiting_approval: 'needs_human_review',
  running: 'evaluating',
  pending: 'unevaluated',
  needs_human_review: 'needs_human_review',
}

export function Agent({ novelId, onOpenNode, notify }: {
  novelId: string
  onOpenNode: (nodeId: string) => void
  notify: (tone: 'success' | 'warning' | 'error' | 'info', message: string) => void
}) {
  const [instruction, setInstruction] = useState('')
  const [scopeKind, setScopeKind] = useState('novel')
  const [scopeUnitId, setScopeUnitId] = useState('')
  const [units, setUnits] = useState<{ node_id: string; label: string }[]>([])
  const [preview, setPreview] = useState<AgentPlanPreviewDto | null>(null)
  const [result, setResult] = useState<AgentResultDto | null>(null)
  const [status, setStatus] = useState<AgentStatusDto | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const sessionId = status?.session.session_id || preview?.session_id || ''

  // scope 需要具体节点时，从 Blueprint 里列出候选（不让模型/前端猜）
  useEffect(() => {
    if (scopeKind === 'novel') return
    const wanted = scopeKind === 'chapter' ? 'chapter' : 'structural_unit'
    void studioApi.blueprint(novelId, wanted).then((payload) => {
      const rows = payload.nodes.map((node) => ({
        node_id: node.node_id,
        label: String(node.visible?.title ?? node.payload?.title ?? node.node_id),
      }))
      setUnits(rows)
      setScopeUnitId((current) => (rows.some((row) => row.node_id === current)
        ? current : (rows[0]?.node_id ?? '')))
    }).catch(() => setUnits([]))
  }, [novelId, scopeKind])

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label)
    setError('')
    try {
      await action()
    } catch (reason) {
      const info = mapError(reason)
      setError(info.message)
      notify('error', info.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <section className="studio-workspace" data-testid="workspace-agent">
      <SectionHeading icon="objective" title="Agent"
        hint="给出目标，Agent 会先给出计划；它会停下来等待你确认重大决定" />

      <Card tone="elevated" testId="agent-goal">
        <label className="studio-field">
          <span>你想要什么？（自然语言只用于描述目标）</span>
          <textarea rows={3} value={instruction} data-testid="agent-goal-input"
            placeholder="例如：把第一幕扩展到 3 个章节，每章至少有 2 个场景，运行质量检查并修复可以自动安全修复的问题，不要自动接受"
            onChange={(event) => setInstruction(event.target.value)} />
        </label>
        <div className="studio-head-actions">
          <label className="studio-field">
            <span>作用范围</span>
            <select value={scopeKind} data-testid="agent-scope"
              onChange={(event) => setScopeKind(event.target.value)}>
              <option value="novel">整本作品</option>
              <option value="structural_unit">某一幕 / 卷 / 弧</option>
              <option value="chapter">某一章</option>
            </select>
          </label>
          {scopeKind !== 'novel' ? (
            <label className="studio-field">
              <span>{scopeKind === 'chapter' ? '哪一章' : '哪一幕 / 卷 / 弧'}</span>
              <select value={scopeUnitId} data-testid="agent-scope-unit"
                onChange={(event) => setScopeUnitId(event.target.value)}>
                {units.map((row) => (
                  <option key={row.node_id} value={row.node_id}>{row.label}</option>
                ))}
              </select>
            </label>
          ) : null}
          <Button variant="primary" icon="creation" testId="agent-plan"
            disabled={instruction.trim().length < 4 || Boolean(busy)
              || (scopeKind !== 'novel' && !scopeUnitId)}
            onClick={() => void run('plan', async () => {
              const payload = await agentApi.plan({
                novel_id: novelId, instruction: instruction.trim(),
                scope_kind: scopeKind, scope_unit_id: scopeUnitId, dry_run: true })
              setPreview(payload)
              setResult(null)
              notify('info', `已生成计划（${payload.preview.length} 步，尚未修改任何内容）`)
            })}>
            {busy === 'plan' ? '规划中…' : '生成计划'}
          </Button>
        </div>
        <p className="studio-muted">
          默认策略：可以生成 / 修改 / 检查 / 修复建议，但不会自动接受，也不会自动交付。
        </p>
      </Card>

      {error ? <p className="studio-error-inline" role="alert">{error}</p> : null}

      {preview ? (
        <Card tone="elevated" testId="agent-plan-preview">
          <header className="studio-tile-head">
            <Icon name="outline" size={20} /><h2>计划预览（还没有修改任何内容）</h2>
            <StatusBadge status={preview.plan.plan_revision > 1 ? 'draft' : 'planned'} />
          </header>
          <ul className="studio-kv">
            <li><span>预计步骤</span><b>{preview.preview.length}</b></li>
            <li><span>其中修改类步骤</span><b>{preview.plan.estimated_mutations}</b></li>
            <li><span>预计模型调用</span><b>{preview.plan.estimated_model_calls}</b></li>
            <li><span>需要你确认</span><b>
              {preview.preview.filter((row) => row.requires_approval).length} 步</b></li>
          </ul>
          <ol className="studio-agent-steps" data-testid="agent-steps">
            {preview.preview.map((step) => (
              <li key={step.step_id} data-testid={`agent-step-${step.sequence}`}>
                <span className="studio-agent-step-index">{step.sequence}</span>
                <div>
                  <b>{ACTION_LABELS[step.action] ?? step.action}</b>
                  <p className="studio-meta">
                    {step.mutation ? '会修改内容' : '只读'}
                    {step.requires_approval ? ' · 需要你确认' : ''}
                    {step.target.node_id ? ` · ${String(step.target.node_id)}` : ''}
                    {step.target.parent_id ? ` · 上级 ${String(step.target.parent_id)}` : ''}
                  </p>
                </div>
              </li>
            ))}
          </ol>
          {(preview.plan.budget_estimate.policy_notes as string[] | undefined)?.length
            ? (
              <p className="studio-warning-line">
                <Icon name="warning" size={15} />
                {(preview.plan.budget_estimate.policy_notes as string[]).join('；')}
              </p>
            ) : null}
          <div className="studio-tile-actions">
            <Button variant="primary" icon="next_action" testId="agent-start"
              disabled={Boolean(busy)}
              onClick={() => void run('start', async () => {
                const payload = await agentApi.start({ session_id: preview.session_id })
                setResult(payload)
                setStatus(await agentApi.status(novelId, preview.session_id))
                notify(payload.status === 'completed' ? 'success'
                  : payload.status === 'awaiting_approval' ? 'warning' : 'info',
                  SUMMARY[payload.status] ?? payload.status)
              })}>
              {busy === 'start' ? '执行中…' : '开始执行'}
            </Button>
            <Button variant="ghost" icon="close"
              onClick={() => { setPreview(null); setResult(null) }}>修改目标</Button>
          </div>
        </Card>
      ) : null}

      {result ? (
        <Card tone="elevated" testId="agent-running">
          <header className="studio-tile-head">
            <Icon name="progress" size={20} /><h2>执行</h2>
            <StatusBadge status={result.status} testId="agent-status" />
          </header>
          <p className="studio-muted">
            {SUMMARY[result.status] ?? result.stop_reason}
          </p>
          <ul className="studio-agent-steps">
            {result.steps.map((step) => (
              <li key={step.step_id} data-testid={`agent-result-${step.action}`}>
                <span className="studio-agent-step-index">
                  <Icon name={step.status === 'completed' ? 'complete'
                    : step.status === 'skipped' ? 'more' : 'warning'} size={16} />
                </span>
                <div>
                  <b>{ACTION_LABELS[step.action] ?? step.action}</b>
                  <p className="studio-meta">
                    <StatusBadge status={STEP_TONE[step.status] ?? step.status} />
                    {' '}{step.message || (step.changed_nodes.length
                      ? `改动 ${step.changed_nodes.length} 个节点` : '')}
                  </p>
                </div>
              </li>
            ))}
          </ul>
          {result.errors.length > 0 ? (
            <p className="studio-warning-line" data-testid="agent-error-code">
              <Icon name="warning" size={15} />
              {result.errors[0].message}（{result.errors[0].code}）
            </p>
          ) : null}
          <div className="studio-head-actions">
            {result.status === 'awaiting_approval' ? (
              <span className="studio-meta">等待你在下面批准，Agent 已停止推进</span>
            ) : null}
            {['awaiting_approval', 'paused', 'failed', 'needs_human_review']
              .includes(result.status) ? (
                <Button variant="secondary" icon="next_action" testId="agent-resume"
                  disabled={Boolean(busy)}
                  onClick={() => void run('resume', async () => {
                    const payload = await agentApi.resume(sessionId)
                    setResult(payload)
                    setStatus(await agentApi.status(novelId, sessionId))
                  })}>继续执行</Button>
              ) : null}
            {['executing', 'awaiting_approval', 'paused', 'needs_human_review']
              .includes(result.status) ? (
                <Button variant="ghost" icon="close" testId="agent-cancel"
                  onClick={() => void run('cancel', async () => {
                    const payload = await agentApi.cancel(sessionId, '作者取消')
                    setResult(payload)
                    notify('info', payload.semantics ?? '已请求取消')
                  })}>取消</Button>
              ) : null}
          </div>
          {result.status === 'completed' ? (
            <div data-testid="agent-completion">
              <h3>完成情况</h3>
              <ul className="studio-kv">
                <li><span>修改的节点</span><b>{result.changed_nodes.length}</b></li>
                <li><span>新增 / 更新版本</span><b>
                  {Object.entries(result.new_revisions)
                    .map(([key, value]) => `${key} r${value}`).join('、') || '—'}</b></li>
                <li><span>质量结论</span><b>
                  {String(result.quality_summary.status ?? '未运行')}</b></li>
                <li><span>需要你继续决定</span><b>
                  {result.needs_human_review ? '是' : '否'}</b></li>
              </ul>
              <p className="studio-muted">
                Agent 不会替你接受内容，也不会自动交付。请到对应页面检查并接受。
              </p>
              <div className="studio-tile-actions">
                {result.changed_nodes.slice(0, 6).map((nodeId) => (
                  <Button key={nodeId} variant="ghost" size="sm" icon="book"
                    onClick={() => onOpenNode(nodeId)}>{nodeId}</Button>
                ))}
              </div>
            </div>
          ) : null}
          <Disclosure summary="执行历史（审计）">
            <ul className="studio-kv">
              {(status?.audit ?? []).map((row, index) => (
                <li key={`${row.operation}-${index}`}>
                  <span>{String(row.operation)}</span>
                  <b className="studio-meta">
                    {String(row.status)} · {String(row.step_id ?? '').slice(0, 14)}
                  </b>
                </li>
              ))}
            </ul>
          </Disclosure>
        </Card>
      ) : null}

      {status && status.pending_approvals.length > 0 ? (
        <Card tone="elevated" testId="agent-approval">
          <header className="studio-tile-head">
            <Icon name="conflict" size={20} /><h2>需要你的确认</h2>
          </header>
          {status.pending_approvals.map((row) => (
            <div key={row.approval_id} className="studio-approval">
              <p><b>{ACTION_LABELS[row.action] ?? row.action}</b>：{row.reason}</p>
              <ul className="studio-kv">
                <li><span>会影响</span><b>
                  {row.affected_nodes.join('、') || '—'}</b></li>
                <li><span>风险</span><b>{row.risk === 'structural'
                  ? '结构级（高层节点）' : '内容级'}</b></li>
                <li><span>基于版本</span><b>
                  {Object.entries(row.revision_refs)
                    .map(([key, value]) => `${key} r${value}`).join('、') || '—'}</b></li>
                <li><span>建议内容</span><b>
                  {Object.entries(row.proposed_after).slice(0, 3)
                    .map(([key, value]) => `${key}: ${String(value)}`).join(' · ')
                    || '—'}</b></li>
              </ul>
              <div className="studio-head-actions">
                <Button variant="primary" icon="complete" testId="agent-approve"
                  disabled={Boolean(busy)}
                  onClick={() => void run('approve', async () => {
                    const payload = await agentApi.approve(sessionId, row.approval_id)
                    setResult(payload)
                    setStatus(await agentApi.status(novelId, sessionId))
                    notify('success', '已批准，Agent 继续执行')
                  })}>批准</Button>
                <Button variant="secondary" icon="close" testId="agent-reject"
                  disabled={Boolean(busy)}
                  onClick={() => void run('reject', async () => {
                    const payload = await agentApi.reject(sessionId, row.approval_id,
                      '作者拒绝')
                    setResult(payload)
                    setStatus(await agentApi.status(novelId, sessionId))
                    notify('info', '已拒绝，Agent 停止推进')
                  })}>拒绝</Button>
              </div>
            </div>
          ))}
          <p className="studio-muted">
            如果你在批准前修改了相关内容，这个请求会过期（需要重新规划）。
          </p>
        </Card>
      ) : null}
    </section>
  )
}

const SUMMARY: Record<string, string> = {
  planning: '计划已生成，等待开始执行',
  executing: '正在执行…',
  awaiting_approval: '有需要你确认的步骤，Agent 已停止等待',
  paused: '执行暂停（预算 / 冲突 / 上限）',
  completed: '目标完成',
  failed: '执行失败（可查看原因后重试）',
  cancelled: '已请求取消',
  needs_human_review: '需要作者决定（不是崩溃）',
}
