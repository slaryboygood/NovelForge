/*
 * NovelForge V4 Story Studio API 客户端（唯一 HTTP 入口）。
 *
 * 规则（`docs/v4/V4_UI_CONTRACT.md` §11）：
 *   · feature 组件不得直接 fetch；一律经本模块
 *   · 只描述 wire 形状；不做任何业务判断（不推断 accepted / 不判断 PASS）
 *   · 错误经 `ApiError`（code + message）→ 由 `studio/design/errors.ts` 映射成作者语言
 */
import { requestJson } from '../api'

/* ------------------------------------------------------------------ 基础 DTO */

export interface StudioNode {
  node_id: string
  node_type: string
  revision: number
  status: string
  parent_id?: string
  sequence?: number
  payload: Record<string, unknown>
  visible: Record<string, unknown>
  review_status?: string
  quality?: Record<string, unknown>
}

export interface StudioOverview {
  novel_id: string
  title: string
  genre: string
  blueprint: {
    node_count: number
    by_type: Record<string, number>
    by_status: Record<string, number>
    accepted: number
    proposed: number
    draft: number
    digest: string
    selection_mode: string
  }
  quality: {
    status: string
    issues: number
    gates: QualityGateRow[]
    open_blockers: number
    summary: Record<string, unknown>
  }
  setup: { counts: Record<string, number>; unpaid_required: number }
  payoff: { counts: Record<string, number> }
  delivery: {
    snapshots: number
    stats: Record<string, unknown>
    last: DeliverySnapshotRow | null
  }
  next_action: {
    action_id?: string
    title?: string
    reason?: string
    impact?: string
    action_label?: string
    target_view?: string
    deep_link?: { view?: string; step?: string; group?: string }
  }
  read_only: boolean
}

export interface QualityGateRow {
  gate: string
  status: 'unevaluated' | 'passed' | 'failed' | 'blocked' | 'skipped' | string
  issues: number
  blockers: number
  duration_ms?: number
  evaluator_ids?: string[]
  skipped_reason?: string
}

export interface QualityIssueRow {
  issue_id: string
  code: string
  gate: string
  severity: 'info' | 'minor' | 'major' | 'blocker' | string
  status: string
  reason: string
  novel_id?: string
  scope?: {
    node_ids?: string[]
    node_types?: string[]
    revision?: number | null
    kind?: string
  }
  evidence?: {
    evidence_id: string
    kind: string
    explanation: string
    node_ids?: string[]
    revision?: number | null
    excerpt?: string
    metric?: Record<string, unknown>
  }[]
  evaluator_id?: string
  evaluator_version?: number
  provenance?: Record<string, unknown>
  repairable?: boolean
}

export interface QualityReportDto {
  report_id: string
  novel_id: string
  status: string
  gates: QualityGateRow[]
  issues: QualityIssueRow[]
  policy: Record<string, unknown>
  usage: Record<string, unknown>
  generated_at: string
  node_revisions: Record<string, number>
  summary?: { status: string; issues: number; blockers: number }
}

export interface QualityCenterDto {
  novel_id: string
  status: string
  gates: QualityGateRow[]
  issues: QualityIssueRow[]
  report: Partial<QualityReportDto> & Record<string, unknown>
  summary: Record<string, unknown>
  policy: Record<string, unknown>
}

export interface RepairPreviewDto {
  status: string
  dry_run?: boolean
  issue_ids?: string[]
  preview?: {
    status?: string
    note?: string
    issues?: string[]
    target_nodes?: string[]
    allowed_fields?: string[]
    preserve_fields?: string[]
    verification_gates?: string[]
    estimated_model_calls?: number
    steps?: { node_id?: string; allow_change?: string[]; preserve?: string[] }[]
  }
  plan?: Record<string, unknown>
  result?: Record<string, unknown> | null
  verification?: VerificationDto | null
}

export interface VerificationDto {
  status: string
  resolved_issue_ids?: string[]
  remaining_issue_ids?: string[]
  regressed_issue_ids?: string[]
  reasons?: string[]
  needs_human_review?: boolean
  report?: { status?: string } | null
}

export interface ExporterRow {
  format: string
  exporter_id: string
  version: number
  mime_type: string
  extension: string
  owner_type: 'core' | 'plugin' | string
  owner_id: string
  profiles_supported?: string[]
  text?: boolean
  description?: string
}

export interface DeliveryFormatsDto {
  novel_id: string
  formats: ExporterRow[]
  format_ids: string[]
  profiles: string[]
  default_formats: string[]
  default_selection_mode: string
  read_only: boolean
}

export interface DeliverySnapshotRow {
  snapshot_id: string
  novel_id?: string
  created_at?: string
  formats?: string[]
  selection_mode?: string
  profile?: string
  status?: string
  manifest_id?: string
}

export interface DeliveryPreflightDto {
  status: string
  ok?: boolean
  novel_id?: string
  snapshot_id?: string
  validation?: {
    ok: boolean
    phase: string
    blocking_reason?: string
    issues?: { code: string; severity: string; message: string }[]
  }
  post_validation?: { ok: boolean; blocking_reason?: string } | null
  artifacts?: {
    format: string
    filename: string
    path: string
    size: number
    checksum: string
    mime_type: string
    exporter_id: string
    exporter_version: number
  }[]
  manifest?: {
    manifest_id: string
    snapshot_id: string
    selected_revisions?: Record<string, number>
    formats?: string[]
    artifacts?: Record<string, unknown>[]
  } | null
  notes?: string[]
  idempotent?: boolean
}

export interface PluginRow {
  plugin_id: string
  name: string
  version: string
  description?: string
  capabilities?: string[]
  permissions?: string[]
  status: string
  compatibility?: Record<string, unknown>
  error_code?: string
  error_message?: string
  approved_version?: string
  approved_permissions?: string[]
  contributions?: Record<string, unknown>[]
  active?: boolean
}

export interface PluginListDto {
  available: boolean
  plugins: PluginRow[]
  trust_model: string
  note: string
  permissions: string[]
  hint?: string
  status?: Record<string, unknown>
  read_only?: boolean
}

export interface EditorNodeDto {
  novel_id: string
  node: StudioNode
  view: {
    node_id: string
    node_type: string
    revision: number
    status: string
    quality_status?: string
    author?: string
    operation?: string
    summary?: string
    changed_fields?: string[]
    review_status?: string
    review_note?: string
  }
  editable_fields: string[]
  protected_fields: string[]
  quality_status: string
  quality?: {
    issues?: QualityIssueRow[]
    historical_issues?: QualityIssueRow[]
    blocking_codes?: string[]
    evaluated?: boolean
  }
}

export interface RevisionHistoryDto {
  novel_id: string
  node_id: string
  current_revision: number
  revision_count: number
  revisions: {
    revision: number
    status: string
    author?: string
    operation?: string
    created_at?: string
    changed_fields?: string[]
    review_status?: string
    summary?: string
  }[]
  operations: Record<string, unknown>[]
  quality?: Record<string, unknown>
  repair_preview?: RepairPreviewDto | null
}

export interface DiffDto {
  node_id: string
  novel_id: string
  revision_before: number
  revision_after: number
  field_changes: { field: string; kind: string; before: unknown; after: unknown }[]
  list_changes?: { field: string; kind: string; added?: unknown[]; removed?: unknown[] }[]
  unchanged_fields?: string[]
  status_before?: string
  status_after?: string
  quality_status_before?: string
  quality_status_after?: string
  digest?: string
  quality?: {
    before_issue_ids?: string[]
    after_issue_ids?: string[]
    resolved_issue_ids?: string[]
    new_issue_ids?: string[]
  }
}

export interface EditResultDto {
  node_id: string
  status: string
  ok?: boolean
  before_revision: number
  revision: number
  changed_fields: string[]
  dry_run?: boolean
  quality_status?: string
  diff?: DiffDto | null
  impact?: ChangeImpactDto | null
  notes?: string[]
  rejected_reason?: string
}

export interface RewriteResultDto extends EditResultDto {
  target_fields: string[]
  violations?: string[]
  model?: string
}

export interface ChangeImpactDto {
  node_id: string
  revision: number
  changed_fields: string[]
  dependent_nodes: string[]
  quality_invalidations: string[]
  summary?: string
  auto_modified?: boolean
}

export interface ApprovalResultDto {
  node_id: string
  decision: 'accepted' | 'rejected' | string
  reviewed_revision: number
  revision: number
  status: string
  quality_status?: string
  review_note?: string
  previous_status?: string
  idempotent?: boolean
  notes?: string[]
  acceptance_note?: string
  quality?: Record<string, unknown>
}

export interface RestoreResultDto {
  node_id: string
  operation: string
  restored_from: number
  before_revision: number
  revision: number
  status: string
  changed_fields: string[]
  notes?: string[]
}

export interface GenerationResultDto {
  ok: boolean
  operation: string
  novel_id: string
  node: StudioNode | null
  revision: number
  contract?: string
  model?: string
  provider?: string
  warnings?: string[]
  next_status?: string
}

export interface NovelSummaryDto {
  novel_id: string
  title: string
  genre?: string
  updated_at?: string
  cast?: number
  factions?: number
}

/* ------------------------------------------------------------------- 客户端 */

const studio = '/api/story-builder/studio'
const editor = '/api/story-builder/editor'
const delivery = '/api/story-builder/delivery'
const legacy = '/api/story-builder'

const q = (params: Record<string, string | number | boolean | undefined>) => {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

const json = (body: unknown) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const studioApi = {
  /* ---------------------------------------------------------------- 读 */
  novels: () => requestJson<{ novels: NovelSummaryDto[] }>(`${legacy}/novels`),
  createNovel: (body: { novel_id: string; title?: string; genre?: string }) =>
    requestJson<NovelSummaryDto>(`${legacy}/novels`, json(body)),
  overview: (novelId: string, mode = 'current') =>
    requestJson<StudioOverview>(`${studio}/overview${q({ novel_id: novelId, mode })}`),
  blueprint: (novelId: string, nodeType = '', mode = 'current') =>
    requestJson<{
      novel_id: string
      selection_mode: string
      node_type: string
      ordering: string[]
      count: number
      nodes: StudioNode[]
      quality_summary: Record<string, unknown>
    }>(`${studio}/blueprint${q({ novel_id: novelId, node_type: nodeType, mode })}`),
  node: (novelId: string, nodeId: string, revision?: number) =>
    requestJson<EditorNodeDto>(
      `${editor}/nodes/${encodeURIComponent(nodeId)}${q({ novel_id: novelId, revision })}`),
  history: (novelId: string, nodeId: string) =>
    requestJson<RevisionHistoryDto>(
      `${editor}/nodes/${encodeURIComponent(nodeId)}/revisions${q({ novel_id: novelId })}`),
  diff: (novelId: string, nodeId: string, fromRevision: number, toRevision?: number) =>
    requestJson<DiffDto>(
      `${editor}/nodes/${encodeURIComponent(nodeId)}/diff${
        q({ novel_id: novelId, from_revision: fromRevision, to_revision: toRevision })}`),
  nodeQuality: (novelId: string, nodeId: string, revision?: number) =>
    requestJson<Record<string, unknown>>(
      `${editor}/nodes/${encodeURIComponent(nodeId)}/quality${
        q({ novel_id: novelId, revision })}`),
  quality: (novelId: string, gate = '', status = '') =>
    requestJson<QualityCenterDto>(`${studio}/quality${q({ novel_id: novelId, gate, status })}`),
  deliveryFormats: (novelId: string) =>
    requestJson<DeliveryFormatsDto>(`${studio}/delivery/formats${q({ novel_id: novelId })}`),
  plugins: () => requestJson<PluginListDto>(`${studio}/plugins`),
  deliverySnapshots: (novelId: string) =>
    requestJson<{ novel_id: string; snapshots: DeliverySnapshotRow[] }>(
      `${delivery}/snapshots${q({ novel_id: novelId })}`),
  deliverySnapshot: (novelId: string, snapshotId: string) =>
    requestJson<Record<string, unknown>>(
      `${delivery}/${encodeURIComponent(snapshotId)}${q({ novel_id: novelId })}`),
  deliveryManifest: (novelId: string, snapshotId: string) =>
    requestJson<Record<string, unknown>>(
      `${delivery}/${encodeURIComponent(snapshotId)}/manifest${q({ novel_id: novelId })}`),
  /* --------------------------------------------------------------- 写 */
  generate: (body: {
    novel_id: string
    task?: string
    node_type?: string
    parent_id?: string
    node_id?: string
    expected_revision?: number
    instruction?: string
    sequence?: number
    /** 兄弟序号（章节 / 单元 / 人物的节点 id 依据；后端 task 契约字段）。 */
    index?: number
    unit_type?: string
    idempotency_key?: string
    dry_run?: boolean
  }) => requestJson<GenerationResultDto>(`${studio}/generate`, json(body)),
  patch: (novelId: string, nodeId: string, body: {
    changes: Record<string, unknown>
    expected_revision?: number
    reason?: string
    idempotency_key?: string
    dry_run?: boolean
  }) => requestJson<EditResultDto>(
    `${editor}/nodes/${encodeURIComponent(nodeId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ novel_id: novelId, ...body }),
    }),
  rewrite: (novelId: string, nodeId: string, body: {
    target_fields: string[]
    instruction: string
    expected_revision?: number
    preserve_fields?: string[]
    quality_issue_ids?: string[]
    dry_run?: boolean
  }) => requestJson<RewriteResultDto>(
    `${editor}/nodes/${encodeURIComponent(nodeId)}/rewrite`,
    json({ novel_id: novelId, ...body })),
  accept: (novelId: string, nodeId: string, body: { revision?: number; reason?: string } = {}) =>
    requestJson<ApprovalResultDto>(
      `${editor}/nodes/${encodeURIComponent(nodeId)}/accept`,
      json({ novel_id: novelId, ...body })),
  reject: (novelId: string, nodeId: string, body: { revision?: number; reason?: string } = {}) =>
    requestJson<ApprovalResultDto>(
      `${editor}/nodes/${encodeURIComponent(nodeId)}/reject`,
      json({ novel_id: novelId, ...body })),
  restore: (novelId: string, nodeId: string, body: { from_revision: number; reason?: string }) =>
    requestJson<RestoreResultDto>(
      `${editor}/nodes/${encodeURIComponent(nodeId)}/restore`,
      json({ novel_id: novelId, ...body })),
  evaluateQuality: (body: { novel_id: string; gates?: string[]; node_ids?: string[] }) =>
    requestJson<QualityReportDto>(`${studio}/quality/evaluate`, json(body)),
  planRepair: (body: { novel_id: string; issue_ids?: string[]; node_id?: string }) =>
    requestJson<RepairPreviewDto>(`${studio}/quality/repair`,
      json({ ...body, dry_run: true })),
  executeRepair: (body: { novel_id: string; issue_ids: string[]; idempotency_key?: string }) =>
    requestJson<RepairPreviewDto>(`${studio}/quality/repair`,
      json({ ...body, dry_run: false })),
  verifyRepair: (body: { novel_id: string; issue_ids?: string[] }) =>
    requestJson<VerificationDto>(`${studio}/quality/verify`, json(body)),
  deliver: (body: {
    novel_id: string
    selection_mode?: string
    profile?: string
    formats: string[]
    require_accepted?: boolean
    require_quality_pass?: boolean
    allow_unevaluated?: boolean
    allow_stale_quality?: boolean
    dry_run?: boolean
    idempotency_key?: string
  }) => requestJson<DeliveryPreflightDto>(delivery, json(body)),
}

/** 交付物下载 URL（浏览器直接下载；仍走同一 REST 契约）。 */
export function deliveryArtifactUrl(novelId: string, snapshotId: string,
  artifactPath: string): string {
  return `${delivery}/${encodeURIComponent(snapshotId)}/artifacts/${
    artifactPath}${q({ novel_id: novelId })}`
}

export type StudioApi = typeof studioApi
