/*
 * Quality Center（§37–§43）。
 *
 * Gate-based，不显示任何总分；issue 以人类文案为主、code 只作诊断；
 * 修复必须先进「预览」（改哪些节点 / 允许改什么 / 保留什么 / 复核哪些 gate）。
 */
import { useState } from 'react'
import type {
  QualityCenterDto, QualityIssueRow, RepairPreviewDto, VerificationDto,
} from '../../api/studio'
import { Button, Card, Disclosure, SectionHeading } from '../../design-system/primitives'
import Icon from '../../design-system/icons/IconRegistry'
import { StatusBadge } from '../design/status'
import { ConfirmDialog, Drawer, IssueCard, SEVERITY_LABELS, issueHumanLabel } from '../components'
import { fieldLabel } from '../design/fields'

export function Quality({
  data, onEvaluate, onPlan, onRepair, onVerify, onOpenNode, busy,
}: {
  data: QualityCenterDto
  onEvaluate: () => void
  onPlan: (issueIds: string[]) => Promise<RepairPreviewDto>
  onRepair: (issueIds: string[]) => Promise<RepairPreviewDto>
  onVerify: (issueIds: string[]) => Promise<VerificationDto>
  onOpenNode: (nodeId: string) => void
  busy: string
}) {
  const [gateFilter, setGateFilter] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [preview, setPreview] = useState<RepairPreviewDto | null>(null)
  const [verification, setVerification] = useState<VerificationDto | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [detail, setDetail] = useState<QualityIssueRow | null>(null)

  const issues = data.issues.filter((row) => !gateFilter || row.gate === gateFilter)
  const repairable = issues.filter((row) => row.status === 'open')
  const selectedIssues = issues.filter((row) => selected.includes(row.issue_id))
  const targets = [...new Set(selectedIssues.flatMap((row) => row.scope?.node_ids ?? []))]

  return (
    <section className="studio-workspace" data-testid="workspace-quality">
      <SectionHeading icon="review" title="检查中心"
        hint="按门禁报告问题；修复只处理你选中的问题"
        action={(
          <div className="studio-head-actions">
            <Button variant="primary" icon="review" onClick={onEvaluate}
              disabled={busy === 'evaluate'} testId="quality-evaluate">
              {busy === 'evaluate' ? '检查中…' : '重新检查'}
            </Button>
            <Button variant="secondary" icon="repair" disabled={selected.length === 0
              || busy === 'plan'}
              onClick={async () => {
                setVerification(null)
                setPreview(await onPlan(selected))
              }}
              testId="quality-plan-repair">
              修复预览（{selected.length}）
            </Button>
          </div>
        )} />

      <Card tone="elevated" className="studio-gate-board" testId="quality-gates">
        <header className="studio-tile-head">
          <Icon name="review" size={20} /><h2>门禁状态</h2>
          <StatusBadge status={data.status} testId="quality-status" />
        </header>
        <ul className="studio-gate-grid">
          {data.gates.map((row) => (
            <li key={row.gate}>
              <button type="button"
                className={`studio-gate-cell is-${row.status}${
                  gateFilter === row.gate ? ' is-active' : ''}`}
                aria-pressed={gateFilter === row.gate}
                onClick={() => setGateFilter(gateFilter === row.gate ? '' : row.gate)}
                data-testid={`gate-${row.gate}`}>
                <span className="studio-gate-code">{row.gate}</span>
                <StatusBadge status={row.status} />
                <span className="studio-meta">
                  {row.issues > 0 ? `${row.issues} 个问题` : '无问题'}
                </span>
              </button>
            </li>
          ))}
        </ul>
        <p className="studio-muted">
          质量结论是「门禁 + 严重度」，没有总分；绿色通过不等于作者已经接受内容。
        </p>
      </Card>

      <section className="studio-issue-board">
        <header className="studio-issue-board-head">
          <h2>问题（{issues.length}）</h2>
          {issues.length > 0 ? (
            <div className="studio-head-actions">
              <Button variant="ghost" size="sm"
                onClick={() => setSelected(repairable.map((row) => row.issue_id))}
                testId="quality-select-all">
                选中可修复的 {repairable.length} 条
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setSelected([])}>清空</Button>
            </div>
          ) : null}
        </header>

        {issues.length === 0 ? (
          <Card tone="quiet" className="studio-empty-card">
            <div className="studio-empty">
              <span className="studio-empty-icon"><Icon name="complete" size={26} /></span>
              <h3>没有发现需要处理的问题</h3>
              <p>{data.status === 'unevaluated'
                ? '还没有做过检查，点「重新检查」生成一份结论。'
                : '当前版本通过了已启用的门禁。'}</p>
            </div>
          </Card>
        ) : (
          <div className="studio-issue-list">
            {issues.map((issue) => (
              <div key={issue.issue_id} className="studio-issue-row">
                <label className="studio-issue-select">
                  <input type="checkbox" checked={selected.includes(issue.issue_id)}
                    disabled={issue.status !== 'open'}
                    onChange={(event) => setSelected(event.target.checked
                      ? [...selected, issue.issue_id]
                      : selected.filter((row) => row !== issue.issue_id))} />
                  <span className="studio-sr-only">选择这条问题</span>
                </label>
                <IssueCard issue={issue} onOpen={() => setDetail(issue)} />
              </div>
            ))}
          </div>
        )}
      </section>

      <Drawer open={Boolean(detail)} title={detail ? issueHumanLabel(detail.code) : ''}
        subtitle={detail ? `${detail.gate} · ${SEVERITY_LABELS[detail.severity]
          ?? detail.severity}` : ''}
        onClose={() => setDetail(null)} testId="issue-drawer"
        footer={detail ? (
          <div className="studio-drawer-actions">
            <Button variant="secondary" icon="repair"
              onClick={() => { setSelected([detail.issue_id]); setDetail(null) }}>
              选中并去修复
            </Button>
          </div>
        ) : null}>
        {detail ? (
          <div className="studio-issue-detail">
            <p>{detail.reason}</p>
            <ul className="studio-kv">
              <li><span>门禁</span><b>{detail.gate}</b></li>
              <li><span>严重度</span><b>{SEVERITY_LABELS[detail.severity]
                ?? detail.severity}</b></li>
              <li><span>状态</span><b>{detail.status}</b></li>
              <li><span>可自动修复</span><b>{detail.repairable ? '是' : '否'}</b></li>
            </ul>
            {detail.scope?.node_ids?.length ? (
              <p className="studio-meta">
                影响节点：
                {detail.scope.node_ids.map((nodeId) => (
                  <button key={nodeId} type="button" className="studio-link"
                    onClick={() => onOpenNode(nodeId)}>{nodeId}</button>
                ))}
              </p>
            ) : null}
            <h4>证据</h4>
            {(detail.evidence ?? []).map((row) => (
              <Card key={row.evidence_id} tone="quiet" className="studio-evidence">
                <p><b>{row.kind}</b>：{row.explanation}</p>
                {row.excerpt ? <blockquote>{row.excerpt}</blockquote> : null}
                {row.metric && Object.keys(row.metric).length > 0 ? (
                  <p className="studio-meta">{Object.entries(row.metric)
                    .map(([key, value]) => `${key}=${String(value)}`).join(' · ')}</p>
                ) : null}
              </Card>
            ))}
            <Disclosure summary="诊断信息">
              <ul className="studio-kv">
                <li><span>issue code</span><b className="studio-code">{detail.code}</b></li>
                <li><span>evaluator</span><b>{detail.evaluator_id || '—'}</b></li>
                <li><span>provenance</span><b>{JSON.stringify(detail.provenance ?? {})}</b></li>
              </ul>
            </Disclosure>
          </div>
        ) : null}
      </Drawer>

      <Drawer open={Boolean(preview)} title="修复预览"
        subtitle="这一步还没有修改任何内容"
        onClose={() => setPreview(null)} testId="repair-preview"
        footer={preview && preview.preview?.status !== 'empty' ? (
          <div className="studio-drawer-actions">
            <Button variant="primary" icon="repair"
              disabled={busy === 'repair'} onClick={() => setConfirming(true)}
              testId="repair-execute">
              {busy === 'repair' ? '修复中…' : '执行修复'}
            </Button>
          </div>
        ) : null}>
        {preview ? <RepairPreviewBody preview={preview} /> : null}
        {verification ? <VerificationBody verification={verification} /> : null}
      </Drawer>

      <ConfirmDialog open={confirming} title="执行修复？"
        body={`将修改 ${targets.length || (preview?.preview?.target_nodes?.length ?? 0)} 个节点，` 
          + '并为每个节点创建新版本（历史不会删除）。修复完成后会自动复核。'}
        confirmLabel="执行修复"
        onCancel={() => setConfirming(false)}
        onConfirm={async () => {
          setConfirming(false)
          const outcome = await onRepair(selected)
          setPreview(outcome)
          const ids = selected
          setVerification(await onVerify(ids))
        }} />
    </section>
  )
}

function RepairPreviewBody({ preview }: { preview: RepairPreviewDto }) {
  const info = preview.preview ?? {}
  if (info.status === 'empty') {
    return <p className="studio-muted">{info.note || '没有可修复的问题。'}</p>
  }
  return (
    <div className="studio-repair-preview">
      <ul className="studio-kv">
        <li><span>将修改节点</span><b>{(info.target_nodes ?? []).join('、') || '—'}</b></li>
        <li><span>允许改动字段</span><b>{(info.allowed_fields ?? [])
          .map((field) => fieldLabel('', field)).join('、') || '—'}</b></li>
        <li><span>必须保留</span><b>{(info.preserve_fields ?? [])
          .map((field) => fieldLabel('', field)).join('、') || '—'}</b></li>
        <li><span>修复后复核</span><b>{(info.verification_gates ?? []).join('、') || '—'}</b></li>
        <li><span>预计模型调用</span><b>{info.estimated_model_calls ?? 0} 次</b></li>
      </ul>
      {info.steps?.length ? (
        <ul className="studio-kv">
          {info.steps.map((step, index) => (
            <li key={`${step.node_id}-${index}`}>
              <span>{step.node_id}</span>
              <b>可改 {(step.allow_change ?? []).join('、') || '—'}</b>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

function VerificationBody({ verification }: { verification: VerificationDto }) {
  const needsAuthor = verification.status === 'needs_human_review'
    || verification.needs_human_review
  return (
    <Card tone="quiet" className="studio-verification" testId="verification-card">
      <header className="studio-tile-head">
        <Icon name={needsAuthor ? 'conflict' : 'complete'} size={18} />
        <h3>{needsAuthor ? '需要作者决定' : '修复复核'}</h3>
        <StatusBadge status={verification.status} />
      </header>
      {verification.resolved_issue_ids?.length ? (
        <p>已解决 {verification.resolved_issue_ids.length} 个问题。</p>
      ) : null}
      {verification.remaining_issue_ids?.length ? (
        <p className="studio-muted">
          仍有 {verification.remaining_issue_ids.length} 个问题需要处理。
        </p>
      ) : null}
      {needsAuthor ? (
        <p className="studio-muted">
          这不是「修复失败」：backend 认为需要作者决定（例如契约冲突或达到轮次上限）。
        </p>
      ) : null}
      {(verification.reasons ?? []).map((reason) => (
        <p key={reason} className="studio-meta">{reason}</p>
      ))}
    </Card>
  )
}
