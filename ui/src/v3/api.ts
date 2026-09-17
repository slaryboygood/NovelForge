/*
 * NovelForge V3 API 客户端（只读投影 + 复用既有 V2 写入口）。
 *
 * 边界：这里只做 HTTP 与 DTO 类型，不做任何业务判断；
 * 写操作全部复用 `src/api.ts` 的既有端点，V3 不新增第二套写 API。
 */
import { api, requestJson } from '../api'

export interface StageDto {
  stage_id: string
  label: string
  icon: string
  goal: string
  /** V3 统一阶段状态。WARNING 保留给「可以进入但需要留意」的真实状态。 */
  status: 'LOCKED' | 'AVAILABLE' | 'CURRENT' | 'IN_PROGRESS' | 'COMPLETE'
    | 'WARNING' | 'BLOCKED'
  progress: { done: number; total: number; percent: number }
  blocked: boolean
  current: boolean
  reachable: boolean
  objective_ids: string[]
}

export interface ObjectiveDto {
  objective_id: string
  stage_id: string
  title: string
  description: string
  why_it_matters: string
  icon: string
  optional: boolean
  blocking: boolean
  status: 'locked' | 'available' | 'active' | 'blocked' | 'complete' | 'optional'
    | 'not_applicable'
  progress: { done: number; total: number; percent: number }
  checklist: { item_id: string; label: string; done: boolean }[]
  completion_evidence: { source: string; ref: string; summary: string }[]
  unlock_effects: string
  target_view: string
  deep_link: { view: string; step?: string; group?: string }
  action_label: string
  truth_layer: string
  read_only: boolean
}

export interface NextActionDto {
  action_id: string
  title: string
  reason: string
  impact: string
  action_label: string
  icon: string
  objective_id: string
  stage_id: string
  deep_link: { view: string; step?: string; group?: string }
  blocking: boolean
  truth_layer: string
  read_only: boolean
}

export interface RiskDto {
  finding_id: string
  level: 'INFO' | 'WARNING' | 'BLOCKING'
  title: string
  detail: string
  hint: string
  source: string
  evidence: Record<string, unknown>
  deep_link: { view: string; step?: string; group?: string }
  action_label: string
  /** P5：这次修复会不会改动故事事实 / 是否可逆（真实存在时才给出）。 */
  approval_label?: string
  reversible?: boolean
}

/** P5：修复中心诊断的作者视图（不暴露 raw patch / payload / opcode）。 */
export interface RepairIssueDto {
  issue_id: string
  title: string
  why: string
  note: string
  target: string
  source_label: string
  approval_label: string
  reversible: boolean
  auto_safe: boolean
}

export interface RepairDto {
  available: boolean
  issue_count: number
  blocking_count: number
  issues: RepairIssueDto[]
  reason: string
}

/** P5：导出就绪度（作者必须知道还缺什么才能交给写作环节）。 */
export interface ExportDto {
  ready: boolean
  headline: string
  steps: { step_id: string; label: string; done: boolean; why: string; view: string }[]
  missing: { step_id: string; label: string; done: boolean; why: string; view: string }[]
  blockers: string[]
  chapter_count: number
  /** 已有写作草稿数量（导出阶段最后一个真实目标）。 */
  writer_drafts: number
  bundle: { label: string; detail: string }[]
}

export interface ContentCardDto {
  card_id: string
  label: string
  icon: string
  count: number
  unit: string
  target_view: string
  hint: string
  truth_layer: 'occurred' | 'planned' | string
  read_only: boolean
}

export interface ActivityDto {
  item_id: string
  label: string
  detail: string
  updated_at: string
  target_view: string
  truth_layer: string
  read_only: boolean
}

/** 大纲层级（book / volume / arc / chapter package）：只读投影，不含内部 provenance。 */
export interface OutlinePackageDto {
  package_id: string
  parent_package_id: string
  level: 'BOOK' | 'VOLUME' | 'ARC' | 'CHAPTER' | string
  title: string
  status: string
  confirmed: boolean
  version: number
  item_count: number
  pending_questions: string[]
}

/** 章节 = 章级大纲包里的一个 item（真实章节，不是 package）。 */
export interface ChapterDto {
  item_id: string
  package_id: string
  parent_package_id: string
  /** 这一章所属篇章的作者可读名称（真实存在时）。 */
  arc_title: string
  order: number
  title: string
  summary: string
  pov: string
  time: string
  location: string
  ending_hook: string
  goals: string[]
  conflicts: string[]
  participants: string[]
  status: string
  confirmed: boolean
  package_version: number
}

export interface OutlineDto {
  started: boolean
  error: string
  book: OutlinePackageDto | null
  volumes: OutlinePackageDto[]
  arcs: OutlinePackageDto[]
  chapter_packages: OutlinePackageDto[]
  chapters: ChapterDto[]
  chapter_count: number
  /** 真实存在的结构缺口（缺哪一级 / 还有多少层级是草稿）。 */
  gaps: string[]
  /** 大纲包自己的待办问题 + 真实的「来源已过期」状态。 */
  warnings: { code: string; message: string; target: string }[]
  /** 锻造质量报告里真实存在的发现（stale 时为空）。 */
  quality: { severity: string; message: string }[]
  /** 故事已推进过、这份大纲是旧版本：必须重新锻造才能与事实一致。 */
  stale: boolean
}

/** 角色实体（作者可读投影；character_id 只作主键与深链接）。 */
export interface CharacterDto {
  character_id: string
  name: string
  /** NF-016：这个名字还是原型占位（设定候选的定位标签），不是作者命名的姓名。 */
  name_placeholder?: boolean
  role_label: string
  kind: string
  is_protagonist: boolean
  status_label: string
  tags: string[]
  active_goals: number
  memories: number
  relationship_count: number
  has_relationships: boolean
  key_relationships: RelationshipEdgeDto[]
}

/** 真实关系边（已发生 StoryState 或设计中内容包；维度值来自 Domain，不换算）。 */
export interface RelationshipEdgeDto {
  source_id: string
  source_label: string
  target_id: string
  target_label: string
  dimension_labels: string[]
  dimension_rows: { label: string; value: number | string }[]
  tags: string[]
  truth_label: string
}

export interface RelationshipsDto {
  available: boolean
  edge_count: number
  occurred_count: number
  planned_count: number
  edges: RelationshipEdgeDto[]
}

export interface CharacterListDto {
  available: boolean
  reason: string
  count: number
  items: CharacterDto[]
  protagonist: CharacterDto | null
  selected_id?: string
}

export interface LocationDto {
  location_id: string
  name: string
  name_placeholder?: boolean
  kind_label: string
  access_label: string
  control_label: string
  danger: number
  current: boolean
  visited: boolean
}

export interface FactionDto {
  faction_id: string
  name: string
  name_placeholder?: boolean
  stance_label: string
  influence: number
  active_plot_count: number
  conflict_count: number
}

export interface WorldDto {
  available: boolean
  reason: string
  locations: LocationDto[]
  factions: FactionDto[]
  current_location: LocationDto | null
  location_count: number
  faction_count: number
}

/** 推演候选方向（来自引擎 runtime_candidates 的真实行动）。 */
export interface RouteCandidateDto {
  candidate_id: string
  title: string
  kind_label: string
  reason: string
  available: boolean
  blocked_reason: string
  requirements: string[]
  costs: string[]
  risks: string[]
  related_characters: string[]
  affected_locations: string[]
  affected_factions: string[]
  goal_notes: string[]
  visibility: string
}

export interface RouteBranchDto {
  branch_id: string
  display_label: string
  official: boolean
  revision: number
  tick: number
}

export interface SimulationDto {
  available: boolean
  reason: string
  tick: number
  revision: number
  branch_id: string
  summary: string
  /** 作者可读的当前状况（地点 / 已登场角色 / 回合）。 */
  situation_rows: { label: string; value: string }[]
  blocked: boolean
  candidates: RouteCandidateDto[]
  branches: RouteBranchDto[]
  runtime_id: string
  /** 世界 / 触发事件 id → 作者可读标题（真实内容包事件卡）。 */
  event_labels: Record<string, string>
}

export interface CommandCenterDto {
  novel: {
    novel_id: string
    title: string
    genre: string
    themes: string[]
    premise: string
    tone: string
    content_pack_id: string
    content_pack_title: string
    updated_at: string
  }
  progress: { percent: number; label: string; done: number; total: number }
  journey: {
    stages: StageDto[]
    current_stage: string
    current_stage_label: string
    current_stage_goal: string
    recommended_next_stage: string
    completed_stages: number
    stage_count: number
  }
  objectives: ObjectiveDto[]
  current_objective: ObjectiveDto | null
  next_action: NextActionDto
  risks: RiskDto[]
  repair: RepairDto
  export: ExportDto
  content: ContentCardDto[]
  activity: ActivityDto[]
  outline: OutlineDto
  characters: CharacterListDto
  world: WorldDto
  relationships: RelationshipsDto
  simulation: SimulationDto
  facts: Record<string, unknown>
  read_only: boolean
  non_authoritative: boolean
}

export interface NovelCardDto {
  novel_id: string
  title: string
  genre: string
  themes: string[]
  updated_at: string
  stage_id: string
  stage_label: string
  progress_percent: number
  progress_done: number
  progress_total: number
  /** 与 Command Center 的「下一步」同源（同一本书同一句话）。 */
  next_action: string
  next_action_label: string
  next_action_view: string
  runtime_started: boolean
  content_pack_id: string
  read_only: boolean
}

/** 导出工作区的真实产物（V3 不新建导出子系统，复用既有 export API）。 */
export interface ExportArtifactDto {
  novel_id: string
  branch_id: string
  validation: { status: string; checks: Record<string, boolean>; section_count: number }
  artifact: {
    filename: string
    format: string
    export_id: string
    content?: string
    content_base64?: string
    size?: number
  }
  read_only: boolean
  non_authoritative: boolean
}

/** writer 草稿一览（preview 层，不写 StoryState / Canon）。 */
export interface WriterDraftDto {
  draft_id: string
  chapter_id: string
  event_id: string
  accepted: boolean
  synced: boolean
  generated_at: string
  truth_layer: string
}

export const v3Api = {
  novels: () => requestJson<{ novels: NovelCardDto[]; count: number }>(
    '/api/story-builder/v3/novels'),
  commandCenter: (novelId: string) => requestJson<CommandCenterDto>(
    `/api/story-builder/v3/novels/${encodeURIComponent(novelId)}/command-center`),
  /** M16A：真实导出包（json / markdown / docx）。 */
  exportPackage: (novelId: string, format: 'markdown' | 'json' | 'docx' = 'markdown',
    branchId = 'main') => requestJson<ExportArtifactDto>(
      `/api/story-builder/export/package?novel_id=${encodeURIComponent(novelId)}`
      + `&branch_id=${encodeURIComponent(branchId)}&format=${format}`),
  /** M16A：writer-ready 包（导出清单 + 分层 writer context）。 */
  writerBundle: (novelId: string, branchId = 'main') => requestJson<Record<string, unknown>>(
    `/api/story-builder/export/writer-bundle?novel_id=${encodeURIComponent(novelId)}`
    + `&branch_id=${encodeURIComponent(branchId)}`),
  /** M16B：写作草稿列表（与投影同源，见 writer store SSOT）。 */
  writerDrafts: (novelId: string) => requestJson<{ novel_id: string; drafts: WriterDraftDto[] }>(
    `/api/story-builder/writer/drafts?novel_id=${encodeURIComponent(novelId)}`),
  /** M16B：创建写作草稿（preview 层；不写事实）。 */
  createWriterDraft: (novelId: string, body: {
    branch_id?: string; chapter_id?: string; event_id?: string; narration?: string;
    style?: Record<string, string>
  }) => requestJson<Record<string, unknown>>(
    `/api/story-builder/writer/drafts?novel_id=${encodeURIComponent(novelId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ novel_id: novelId, ...body }),
    }),
  /** NF-011：重命名作品（只改名字）。 */
  renameNovel: (novelId: string, title: string) => requestJson<Record<string, unknown>>(
    `/api/story-builder/novels/${encodeURIComponent(novelId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    }),
  /** NF-011：删除作品＝整体归档（二次确认；后端不回滚，但归档可恢复）。 */
  deleteNovel: (novelId: string, reason = '') => requestJson<Record<string, unknown>>(
    `/api/story-builder/novels/${encodeURIComponent(novelId)}?confirm=true`
    + `&reason=${encodeURIComponent(reason)}`, { method: 'DELETE' }),
}

/** 创作流程的写入口：全部复用既有 V2 API（V3 不新增写语义）。 */
export const v3Writes = {
  creativeBrief: api.creativeBrief,
  creativeSuggest: api.creativeSuggest,
  saveCreativeBrief: api.saveCreativeBrief,
  settingSeed: api.settingSeed,
  suggestSettingSeed: api.suggestSettingSeed,
  saveSettingSeed: api.saveSettingSeed,
  runSettingsCheck: api.runSettingsCheck,
  settingsCheck: api.settingsCheck,
  startRuntime: api.startRuntime,
  /** 推演推进：复用既有 runtime/advance（V3 不新增推演引擎）。 */
  advanceRuntime: api.advanceRuntime,
  guidedFlow: api.guidedFlow,
  storyBuilderCreateNovel: api.storyBuilderCreateNovel,
  storyBuilderContentPacks: api.storyBuilderContentPacks,
  storyBuilderNovels: api.storyBuilderNovels,
}

export type { CreativeBrief, SettingSeed, SettingsCheckReport } from '../api'
