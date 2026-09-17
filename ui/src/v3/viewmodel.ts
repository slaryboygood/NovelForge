/*
 * NovelForge V3 ViewModel 层。
 *
 * 输入只有 application 投影（`v3/api.ts` 的 DTO），输出 UI 直接渲染的 ViewModel。
 * 这里允许做：文案拼接、状态 → 颜色/图标语义映射、时间格式化、排序。
 * 这里禁止做：解析 StoryState / Canon、计算 stage 或 objective 是否完成、
 * 判断 repair 权限、推导规划真值——那些全部来自 application 投影。
 */
import type {
  ActivityDto, CommandCenterDto, ContentCardDto, NextActionDto, NovelCardDto,
  ChapterDto, CharacterDto, CharacterListDto, FactionDto, LocationDto, ObjectiveDto,
  ExportDto, OutlineDto, OutlinePackageDto, RelationshipEdgeDto, RepairDto,
  RiskDto, StageDto, WorldDto,
  RouteBranchDto, RouteCandidateDto, SimulationDto,
} from './api'
import { resolveEntityArtwork } from './design-system/assets/artworkManifest'

export interface StageViewModel {
  stageId: string
  label: string
  icon: string
  goal: string
  statusClass: string
  statusLabel: string
  current: boolean
  reachable: boolean
  progressLabel: string
  progressPercent: number
}

export interface ChecklistViewModel {
  itemId: string
  label: string
  done: boolean
  optional: boolean
}

export interface ObjectiveViewModel {
  objectiveId: string
  stageId: string
  title: string
  description: string
  why: string
  icon: string
  statusClass: string
  statusLabel: string
  optional: boolean
  blocking: boolean
  recommended: boolean
  percent: number
  progress: { done: number; total: number }
  progressLabel: string
  checklist: ChecklistViewModel[]
  hint: string
  unlockEffects: string
  actionLabel: string
  deepLink: { view: string; step?: string; group?: string }
  evidence: { source: string; ref: string; summary: string }[]
}

export interface NextActionViewModel {
  actionId: string
  title: string
  reason: string
  impact: string
  actionLabel: string
  icon: string
  blocking: boolean
  deepLink: { view: string; step?: string; group?: string }
}

export interface AlertViewModel {
  alertId: string
  level: 'INFO' | 'WARNING' | 'BLOCKING'
  levelLabel: string
  title: string
  detail: string
  hint: string
  actionLabel: string
  deepLink: { view: string; step?: string; group?: string }
  source: string
  /** P5：修复会不会改动故事事实 / 是否可逆（真实存在时才给出）。 */
  fixLabel: string
  reversibleLabel: string
}

/** P5：修复中心的作者视图（不暴露 raw patch / payload / opcode）。 */
export interface RepairIssueViewModel {
  issueId: string
  title: string
  why: string
  sourceLabel: string
  approvalLabel: string
  reversibleLabel: string
}

export interface RepairViewModel {
  available: boolean
  issueCount: number
  blockingCount: number
  issues: RepairIssueViewModel[]
  reason: string
}

/** P5：导出就绪度（还缺什么才能交给写作环节）。 */
export interface ExportViewModel {
  ready: boolean
  headline: string
  steps: { stepId: string; label: string; done: boolean; why: string; view: string }[]
  missing: { stepId: string; label: string; why: string; view: string }[]
  blockers: string[]
  chapterCount: number
  writerDrafts: number
  bundle: { label: string; detail: string }[]
}

export interface ContentCardViewModel {
  cardId: string
  label: string
  icon: string
  count: number
  unit: string
  hint: string
  targetView: string
  truthLabel: string
}

export interface RecentItemViewModel {
  itemId: string
  label: string
  detail: string
  updatedLabel: string
  icon: string
  targetView: string
}

export interface HeroViewModel {
  novelId: string
  title: string
  tags: string[]
  premise: string
  progressPercent: number
  progressLabel: string
  stageLabel: string
  stageProgressLabel: string
  continueLabel: string
  /** 作品 Hero 视觉：真实作品视觉缺失时走 Product Default Artwork。 */
  visual: EntityVisualViewModel
}

/** 章节实体（作者视角）：标题 / 顺序 / 目的 / 状态 / 可点击。 */
export interface ChapterViewModel {
  chapterId: string
  packageId: string
  /** 所属篇章名称（真实存在时），用于让章节知道自己在大纲的什么位置。 */
  arcTitle: string
  order: number
  /** 章节视觉（真实章节插画缺失时走 Product Default Artwork → 语义图标）。 */
  visual: EntityVisualViewModel
  title: string
  summary: string
  statusLabel: string
  statusTone: 'success' | 'primary' | 'warning' | 'neutral'
  confirmed: boolean
  metaLabel: string
  hook: string
  goals: string[]
  conflicts: string[]
  participants: string[]
  canvasLabel: string
  packageVersion: number
}

export interface OutlineViewModel {
  started: boolean
  bookTitle: string
  bookStatusLabel: string
  bookConfirmed: boolean
  volumeCount: number
  arcCount: number
  chapterCount: number
  /** 大纲层级（作者视角）：全书 → 卷 → 篇章 → 章纲。 */
  levels: {
    level: string
    label: string
    count: number
    statusLabel: string
    confirmed: boolean
  }[]
  volumes: { packageId: string; title: string; statusLabel: string; confirmed: boolean }[]
  arcs: { packageId: string; title: string; statusLabel: string; confirmed: boolean }[]
  chapters: ChapterViewModel[]
  /** 全书主线已存在但没有章纲：这时章节不是错误，只是还没锻造。 */
  hasChapterPlan: boolean
  /** 真实存在的结构缺口（缺哪一级 / 哪些层级还是草稿）。 */
  gaps: string[]
  /** 真实存在的大纲警告（待办问题 / 来源已过期）。 */
  warnings: { code: string; message: string }[]
  /** 锻造质量报告里真实存在的发现。 */
  quality: { severity: string; message: string }[]
  /** 故事已推进过，大纲已过期：应当重新锻造。 */
  stale: boolean
}

/**
 * 实体视觉契约（P2 §7）。
 *
 * 角色 / 地点 / 势力 / 章节 / 作品共用这一种描述：组件不许各自写渐变或占位图，
 * fallback 由设计系统的 EntityVisual 统一渲染。当前项目没有真实图片资源，
 * 因此 imageUrl 保持为空、hasArtwork=false，走统一的 placeholder。
 */
export interface EntityVisualViewModel {
  kind: 'character' | 'location' | 'faction' | 'chapter' | 'novel' | 'hero' | 'route'
  imageUrl: string
  icon: string
  hasArtwork: boolean
  /** 视觉来源：story（真实作品资源）/ default（产品默认资源）/ icon（语义图标）。 */
  source: 'story' | 'default' | 'icon'
}

export interface CharacterEntityViewModel {
  characterId: string
  name: string
  /** 名字还是原型占位（设定候选的定位标签）。 */
  namePlaceholder: boolean
  roleLabel: string
  isProtagonist: boolean
  statusLabel: string
  tags: string[]
  activeGoals: number
  memories: number
  relationshipCount: number
  hasRelationships: boolean
  /** 最多 3 条真实关键关系（详情在 ContextPanel）。 */
  keyRelationships: RelationshipViewModel[]
  visual: EntityVisualViewModel
  /** 真实事实摘要（有才算，不伪造进度百分比）。 */
  factsLabel: string
}

export interface RelationshipViewModel {
  sourceId: string
  sourceLabel: string
  targetId: string
  targetLabel: string
  /** 「甲 ↔ 乙」的作者可读形式。 */
  pairLabel: string
  /** 真实维度（信任 / 敌意 …）及其 Domain 值，不做阈值换算。 */
  dimensionRows: { label: string; value: number | string }[]
  tags: string[]
  truthLabel: string
}

export interface LocationEntityViewModel {
  locationId: string
  name: string
  namePlaceholder: boolean
  kindLabel: string
  accessLabel: string
  controlLabel: string
  danger: number
  current: boolean
  visited: boolean
  visual: EntityVisualViewModel
  factsLabel: string
}

export interface FactionEntityViewModel {
  factionId: string
  name: string
  namePlaceholder: boolean
  stanceLabel: string
  influence: number
  activePlotCount: number
  conflictCount: number
  visual: EntityVisualViewModel
  factsLabel: string
}

export interface CharactersViewModel {
  available: boolean
  count: number
  items: CharacterEntityViewModel[]
  protagonist: CharacterEntityViewModel | null
}

export interface WorldViewModel {
  available: boolean
  locations: LocationEntityViewModel[]
  factions: FactionEntityViewModel[]
  currentLocation: LocationEntityViewModel | null
  locationCount: number
  factionCount: number
}

/** 推演候选方向（Route Visual Entity 的 ViewModel）。 */
export interface RouteCandidateViewModel {
  candidateId: string
  title: string
  kindLabel: string
  reason: string
  available: boolean
  blockedReason: string
  requirements: string[]
  costs: string[]
  risks: string[]
  relatedCharacters: string[]
  affectedLocations: string[]
  affectedFactions: string[]
  stateLabel: string
  visibility: string
  visual: EntityVisualViewModel
}

export interface RouteBranchViewModel {
  branchId: string
  displayLabel: string
  official: boolean
  revision: number
  tick: number
}

export interface SimulationViewModel {
  available: boolean
  reason: string
  tick: number
  revision: number
  branchId: string
  summary: string
  /** 作者可读的当前状况（地点 / 已登场角色 / 回合）。 */
  situationRows: { label: string; value: string }[]
  blocked: boolean
  candidates: RouteCandidateViewModel[]
  branches: RouteBranchViewModel[]
  /** 世界事件 id → 标题（用于把引擎 id 翻成作者语言；缺失时退回数量描述）。 */
  eventLabels: Record<string, string>
  /** 已经推演过至少一轮（真实 revision > 0）。 */
  hasAdvanced: boolean
}

export interface CommandCenterViewModel {
  hero: HeroViewModel
  stages: StageViewModel[]
  objectives: ObjectiveViewModel[]
  currentObjective: ObjectiveViewModel | null
  nextAction: NextActionViewModel
  alerts: AlertViewModel[]
  repair: RepairViewModel
  exportView: ExportViewModel
  content: ContentCardViewModel[]
  recent: RecentItemViewModel[]
  outline: OutlineViewModel
  characters: CharactersViewModel
  world: WorldViewModel
  simulation: SimulationViewModel
  facts: {
    creativeBriefSaved: boolean
    settingSeedSaved: boolean
    contentPackReady: boolean
    settingsCheckOk: boolean
    runtimeStarted: boolean
  }
  isEmptyProject: boolean
  currentStageId: string
}

export interface LandingCardViewModel {
  novelId: string
  title: string
  tags: string[]
  stageLabel: string
  progressPercent: number
  progressLabel: string
  nextAction: string
  updatedLabel: string
  stageIcon: string
  /** 作品视觉：真实封面缺失时走 Product Default Artwork（不按作品名猜图）。 */
  visual: EntityVisualViewModel
}

const OBJECTIVE_STATUS_LABEL: Record<string, string> = {
  complete: '已完成',
  active: '进行中',
  available: '可以开始',
  blocked: '需要处理',
  locked: '尚未开放',
  optional: '可选',
  not_applicable: '暂不需要',
}

const LEVEL_LABEL: Record<string, string> = {
  INFO: '提示',
  WARNING: '留意',
  BLOCKING: '阻塞',
}

const TRUTH_LABEL: Record<string, string> = {
  occurred: '已发生',
  planned: '设计中',
}

const ACTIVITY_ICON: Record<string, string> = {
  activity_idea: 'creation',
  activity_settings: 'world',
  activity_pack: 'story',
  activity_runtime: 'simulation',
  activity_outline: 'outline',
}

const OUTLINE_STATUS_LABEL: Record<string, string> = {
  DRAFT: '草稿',
  REVIEW: '待确认',
  NEEDS_REVIEW: '待复核',
  CONFIRMED: '已确认',
  SUPERSEDED: '已有新版本',
}

const OUTLINE_STATUS_TONE: Record<string, 'success' | 'primary' | 'warning' | 'neutral'> = {
  DRAFT: 'neutral',
  REVIEW: 'warning',
  NEEDS_REVIEW: 'warning',
  CONFIRMED: 'success',
  SUPERSEDED: 'neutral',
}

const STAGE_ICON_FALLBACK: Record<string, string> = {
  creation: 'creation',
  world: 'world',
  characters: 'character',
  story: 'story',
  simulation: 'simulation',
  outline: 'outline',
  review: 'review',
  export: 'export',
}

export function relativeTime(iso: string): string {
  if (!iso) return ''
  const stamp = Date.parse(iso)
  if (Number.isNaN(stamp)) return ''
  const minutes = Math.round((Date.now() - stamp) / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days} 天前`
  return new Date(stamp).toLocaleDateString('zh-CN')
}

function stageViewModel(stage: StageDto): StageViewModel {
  return {
    stageId: stage.stage_id,
    label: stage.label,
    icon: stage.icon || STAGE_ICON_FALLBACK[stage.stage_id] || 'current',
    goal: stage.goal,
    statusClass: stage.status,
    statusLabel: stage.status === 'CURRENT' ? '进行中'
      : stage.status === 'IN_PROGRESS' ? '进行中'
      : stage.status === 'COMPLETE' ? '已完成'
      : stage.status === 'AVAILABLE' ? '可以进入'
      : stage.status === 'LOCKED' ? '尚未开放'
      : stage.status === 'BLOCKED' ? '需要处理'
      : stage.status === 'WARNING' ? '需要留意'
      : '需要留意',
    current: stage.current,
    reachable: stage.reachable,
    progressLabel: `${stage.progress.done} / ${stage.progress.total}`,
    progressPercent: stage.progress.percent,
  }
}

export function objectiveViewModel(objective: ObjectiveDto,
  recommendedIds: Set<string>): ObjectiveViewModel {
  const checklist = objective.checklist.map((row) => ({
    itemId: row.item_id,
    label: row.label,
    done: row.done,
    optional: objective.optional && !row.done,
  }))
  return {
    objectiveId: objective.objective_id,
    stageId: objective.stage_id,
    title: objective.title,
    description: objective.description,
    why: objective.why_it_matters,
    icon: objective.icon,
    statusClass: objective.status,
    statusLabel: OBJECTIVE_STATUS_LABEL[objective.status] ?? objective.status,
    optional: objective.optional,
    blocking: objective.blocking,
    recommended: recommendedIds.has(objective.objective_id),
    percent: objective.progress.percent,
    progress: { done: objective.progress.done, total: objective.progress.total },
    progressLabel: `${objective.progress.done} / ${objective.progress.total}`,
    checklist,
    hint: checklist.length === 0 ? objective.description : '',
    unlockEffects: objective.unlock_effects,
    actionLabel: objective.action_label,
    deepLink: objective.deep_link,
    evidence: objective.completion_evidence ?? [],
  }
}

function nextActionViewModel(action: NextActionDto): NextActionViewModel {
  return {
    actionId: action.action_id,
    title: action.title,
    reason: action.reason,
    impact: action.impact,
    actionLabel: action.action_label,
    icon: action.icon,
    blocking: action.blocking,
    deepLink: action.deep_link,
  }
}

function alertViewModel(risk: RiskDto): AlertViewModel {
  return {
    alertId: risk.finding_id,
    level: risk.level,
    levelLabel: LEVEL_LABEL[risk.level] ?? risk.level,
    title: risk.title,
    detail: risk.detail,
    hint: risk.hint,
    actionLabel: risk.action_label,
    deepLink: risk.deep_link,
    source: risk.source,
    fixLabel: risk.approval_label ?? '',
    reversibleLabel: risk.reversible === undefined ? ''
      : risk.reversible ? '可以回退' : '回退会影响已发生的内容',
  }
}

function repairViewModel(repair: RepairDto | undefined): RepairViewModel {
  return {
    available: Boolean(repair?.available),
    issueCount: repair?.issue_count ?? 0,
    blockingCount: repair?.blocking_count ?? 0,
    reason: repair?.reason ?? '',
    issues: (repair?.issues ?? []).map((row) => ({
      issueId: row.issue_id,
      title: row.title,
      why: row.why || row.note,
      sourceLabel: row.source_label,
      approvalLabel: row.approval_label,
      reversibleLabel: row.reversible ? '可以回退' : '回退会影响已发生的内容',
    })),
  }
}

function exportViewModel(payload: ExportDto | undefined): ExportViewModel {
  return {
    ready: Boolean(payload?.ready),
    headline: payload?.headline ?? '',
    steps: (payload?.steps ?? []).map((row) => ({
      stepId: row.step_id, label: row.label, done: row.done, why: row.why, view: row.view,
    })),
    missing: (payload?.missing ?? []).map((row) => ({
      stepId: row.step_id, label: row.label, why: row.why, view: row.view,
    })),
    blockers: payload?.blockers ?? [],
    chapterCount: payload?.chapter_count ?? 0,
    writerDrafts: payload?.writer_drafts ?? 0,
    bundle: (payload?.bundle ?? []).map((row) => ({ label: row.label, detail: row.detail })),
  }
}

function contentViewModel(card: ContentCardDto): ContentCardViewModel {
  return {
    cardId: card.card_id,
    label: card.label,
    icon: card.icon,
    count: card.count,
    unit: card.unit,
    hint: card.hint,
    targetView: card.target_view,
    truthLabel: TRUTH_LABEL[card.truth_layer] ?? '',
  }
}

function recentViewModel(item: ActivityDto): RecentItemViewModel {
  return {
    itemId: item.item_id,
    label: item.label,
    detail: item.detail,
    updatedLabel: relativeTime(item.updated_at),
    icon: ACTIVITY_ICON[item.item_id] ?? 'chapter',
    targetView: item.target_view,
  }
}

function chapterViewModel(row: ChapterDto): ChapterViewModel {
  const meta = [row.pov, row.time, row.location].filter((value) => value && value.trim())
  return {
    chapterId: row.item_id,
    packageId: row.package_id,
    arcTitle: (row.arc_title || '').trim(),
    order: row.order,
    visual: entityVisual('chapter'),
    // 作者语言优先：标题 → 顺序 fallback → 机器 id 只作为最后兜底。
    title: (row.title || '').trim() || `第 ${row.order} 章`,
    summary: (row.summary || '').trim(),
    statusLabel: OUTLINE_STATUS_LABEL[row.status] ?? '草稿',
    statusTone: OUTLINE_STATUS_TONE[row.status] ?? 'neutral',
    confirmed: row.confirmed,
    metaLabel: meta.join(' · '),
    hook: (row.ending_hook || '').trim(),
    goals: row.goals ?? [],
    conflicts: row.conflicts ?? [],
    participants: row.participants ?? [],
    canvasLabel: row.item_id || row.package_id,
    packageVersion: row.package_version,
  }
}

function outlineViewModel(outline: OutlineDto | undefined): OutlineViewModel {
  const chapters = (outline?.chapters ?? []).map(chapterViewModel)
  const statusOf = (row: OutlinePackageDto | null | undefined) =>
    OUTLINE_STATUS_LABEL[row?.status ?? ''] ?? '草稿'
  const book = outline?.book ?? null
  const volumes = (outline?.volumes ?? []).map((row) => ({
    packageId: row.package_id, title: row.title, statusLabel: statusOf(row),
    confirmed: row.confirmed,
  }))
  const arcs = (outline?.arcs ?? []).map((row) => ({
    packageId: row.package_id, title: row.title, statusLabel: statusOf(row),
    confirmed: row.confirmed,
  }))
  return {
    started: Boolean(outline?.started),
    bookTitle: book?.title ?? '',
    bookStatusLabel: statusOf(book),
    bookConfirmed: Boolean(book?.confirmed),
    volumeCount: volumes.length,
    arcCount: arcs.length,
    chapterCount: outline?.chapter_count ?? chapters.length,
    // 四级结构的作者视图：缺哪一级都真实显示为 0，不补假数字。
    levels: [
      { level: 'book', label: '全书主线', count: book ? 1 : 0, statusLabel: statusOf(book),
        confirmed: Boolean(book?.confirmed) },
      { level: 'volume', label: '卷纲', count: volumes.length, statusLabel: '',
        confirmed: volumes.length > 0 && volumes.every((row) => row.confirmed) },
      { level: 'arc', label: '篇章纲', count: arcs.length, statusLabel: '',
        confirmed: arcs.length > 0 && arcs.every((row) => row.confirmed) },
      { level: 'chapter', label: '详细章纲', count: outline?.chapter_count ?? chapters.length,
        statusLabel: '', confirmed: chapters.length > 0
          && chapters.every((row) => row.confirmed) },
    ],
    volumes,
    arcs,
    chapters,
    hasChapterPlan: (outline?.chapter_packages?.length ?? 0) > 0,
    gaps: outline?.gaps ?? [],
    warnings: (outline?.warnings ?? []).map((row) => ({ code: row.code, message: row.message })),
    quality: (outline?.quality ?? []).map((row) => ({
      severity: row.severity, message: row.message,
    })),
    stale: Boolean(outline?.stale),
  }
}

/** 视觉语义 → 统一图标。没有真实图片时，EntityVisual 用这个图标渲染 placeholder。 */
const ENTITY_ICON: Record<EntityVisualViewModel['kind'], string> = {
  character: 'character',
  location: 'location',
  faction: 'faction',
  chapter: 'chapter',
  novel: 'book',
  hero: 'book',
  route: 'route',
}

export function entityVisual(kind: EntityVisualViewModel['kind'],
  imageUrl = ''): EntityVisualViewModel {
  /**
   * 视觉解析统一走 Artwork Manifest（real story asset → product default → semantic icon），
   * 组件不自己存路径，也不按作品名 / 角色名 / 地点名猜图。
   *
   * 说明：当前 Domain 还没有任何 artwork 字段（NovelProfile / 内容包都不含 cover /
   * portrait / emblem），因此 `imageUrl` 目前始终为空，展示的是 Product Default Artwork；
   * 一旦投影给出真实资源 URL，这里会自动优先使用它。
   */
  const resolved = resolveEntityArtwork(kind === 'novel' ? 'novelCover' : kind, imageUrl)
  return {
    kind,
    imageUrl: resolved.imageUrl,
    icon: ENTITY_ICON[kind],
    hasArtwork: Boolean(resolved.imageUrl),
    source: resolved.source,
  }
}

function characterEntityViewModel(row: CharacterDto): CharacterEntityViewModel {
  const facts: string[] = []
  if (row.active_goals > 0) facts.push(`${row.active_goals} 个进行中的目标`)
  if (row.memories > 0) facts.push(`${row.memories} 条记忆`)
  return {
    characterId: row.character_id,
    name: row.name,
    namePlaceholder: Boolean(row.name_placeholder),
    roleLabel: row.role_label,
    isProtagonist: row.is_protagonist,
    statusLabel: row.status_label,
    tags: row.tags ?? [],
    activeGoals: row.active_goals,
    memories: row.memories,
    relationshipCount: row.relationship_count ?? 0,
    hasRelationships: Boolean(row.has_relationships),
    keyRelationships: (row.key_relationships ?? []).map(relationshipViewModel),
    visual: entityVisual('character'),
    factsLabel: facts.join(' · '),
  }
}

function relationshipViewModel(row: RelationshipEdgeDto): RelationshipViewModel {
  return {
    sourceId: row.source_id,
    sourceLabel: row.source_label,
    targetId: row.target_id,
    targetLabel: row.target_label,
    pairLabel: `${row.source_label} ↔ ${row.target_label}`,
    dimensionRows: row.dimension_rows ?? [],
    tags: row.tags ?? [],
    truthLabel: row.truth_label,
  }
}

function charactersViewModel(data: CharacterListDto | undefined): CharactersViewModel {
  const items = (data?.items ?? []).map(characterEntityViewModel)
  const protagonist = data?.protagonist
    ? items.find((row) => row.characterId === data.protagonist?.character_id) ?? null
    : null
  return {
    available: Boolean(data?.available),
    count: data?.count ?? items.length,
    items,
    protagonist,
  }
}

function locationEntityViewModel(row: LocationDto): LocationEntityViewModel {
  const facts: string[] = []
  if (row.danger > 0) facts.push(`危险度 ${row.danger}`)
  if (row.access_label) facts.push(row.access_label)
  return {
    locationId: row.location_id,
    name: row.name,
    namePlaceholder: Boolean(row.name_placeholder),
    kindLabel: row.kind_label,
    accessLabel: row.access_label,
    controlLabel: row.control_label,
    danger: row.danger,
    current: row.current,
    visited: row.visited,
    visual: entityVisual('location'),
    factsLabel: facts.join(' · '),
  }
}

function factionEntityViewModel(row: FactionDto): FactionEntityViewModel {
  const facts: string[] = [`影响力 ${row.influence}`]
  if (row.active_plot_count > 0) facts.push(`参与 ${row.active_plot_count} 条线`)
  if (row.conflict_count > 0) facts.push(`${row.conflict_count} 处内部冲突`)
  return {
    factionId: row.faction_id,
    name: row.name,
    namePlaceholder: Boolean(row.name_placeholder),
    stanceLabel: row.stance_label,
    influence: row.influence,
    activePlotCount: row.active_plot_count,
    conflictCount: row.conflict_count,
    visual: entityVisual('faction'),
    factsLabel: facts.join(' · '),
  }
}

function worldViewModel(data: WorldDto | undefined): WorldViewModel {
  const locations = (data?.locations ?? []).map(locationEntityViewModel)
  const currentId = data?.current_location?.location_id ?? ''
  return {
    available: Boolean(data?.available),
    locations,
    factions: (data?.factions ?? []).map(factionEntityViewModel),
    currentLocation: locations.find((row) => row.locationId === currentId) ?? null,
    locationCount: data?.location_count ?? locations.length,
    factionCount: data?.faction_count ?? (data?.factions ?? []).length,
  }
}

function routeCandidateViewModel(row: RouteCandidateDto): RouteCandidateViewModel {
  return {
    candidateId: row.candidate_id,
    title: row.title,
    kindLabel: row.kind_label,
    reason: row.reason,
    available: row.available,
    blockedReason: row.blocked_reason,
    requirements: row.requirements ?? [],
    costs: row.costs ?? [],
    risks: row.risks ?? [],
    relatedCharacters: row.related_characters ?? [],
    affectedLocations: row.affected_locations ?? [],
    affectedFactions: row.affected_factions ?? [],
    stateLabel: row.available ? '现在可以做' : '条件未满足',
    visibility: row.visibility,
    visual: entityVisual('route'),
  }
}

function routeBranchViewModel(row: RouteBranchDto): RouteBranchViewModel {
  return {
    branchId: row.branch_id,
    displayLabel: row.display_label,
    official: row.official,
    revision: row.revision,
    tick: row.tick,
  }
}

function simulationViewModel(data: SimulationDto | undefined): SimulationViewModel {
  const revision = data?.revision ?? 0
  return {
    available: Boolean(data?.available),
    reason: data?.reason ?? '还不能推演',
    tick: data?.tick ?? 0,
    revision,
    branchId: data?.branch_id ?? '',
    summary: data?.summary ?? '',
    situationRows: data?.situation_rows ?? [],
    blocked: Boolean(data?.blocked),
    candidates: (data?.candidates ?? []).map(routeCandidateViewModel),
    branches: (data?.branches ?? []).map(routeBranchViewModel),
    eventLabels: data?.event_labels ?? {},
    hasAdvanced: revision > 0,
  }
}

/** 路线比较行：只比较真实存在、且真实有差异的维度（不制造假差异）。 */
export interface RouteComparisonRow {
  label: string
  left: string
  right: string
  differs: boolean
}

function joinOrNone(values: string[]): string {
  return values.length > 0 ? values.join('、') : '无'
}

export function compareRoutes(left: RouteCandidateViewModel,
  right: RouteCandidateViewModel): RouteComparisonRow[] {
  const rows: RouteComparisonRow[] = [
    { label: '方向类型', left: left.kindLabel, right: right.kindLabel },
    { label: '现在能不能做', left: left.stateLabel, right: right.stateLabel },
    { label: '前置条件', left: joinOrNone(left.requirements), right: joinOrNone(right.requirements) },
    { label: '代价', left: joinOrNone(left.costs), right: joinOrNone(right.costs) },
    { label: '风险', left: joinOrNone(left.risks), right: joinOrNone(right.risks) },
    { label: '影响角色', left: joinOrNone(left.relatedCharacters), right: joinOrNone(right.relatedCharacters) },
    { label: '影响地点', left: joinOrNone(left.affectedLocations), right: joinOrNone(right.affectedLocations) },
    { label: '影响势力', left: joinOrNone(left.affectedFactions), right: joinOrNone(right.affectedFactions) },
  ].map((row) => ({ ...row, differs: row.left !== row.right }))
  // 有真实差异的维度排前面；两边都是「无」的维度直接不显示。
  return rows.filter((row) => !(row.left === '无' && row.right === '无'))
    .sort((a, b) => Number(b.differs) - Number(a.differs))
}

export function commandCenterViewModel(data: CommandCenterDto): CommandCenterViewModel {
  const recommendedIds = new Set<string>()
  if (data.next_action.objective_id) recommendedIds.add(data.next_action.objective_id)
  if (data.current_objective) recommendedIds.add(data.current_objective.objective_id)
  const objectives = data.objectives.map((row) => objectiveViewModel(row, recommendedIds))
  const currentObjective = data.current_objective
    ? objectives.find((row) => row.objectiveId === data.current_objective?.objective_id) ?? null
    : null
  const tags = [data.novel.genre, ...(data.novel.themes ?? [])].filter(Boolean).slice(0, 4)
  const stageProgress = data.journey.stages.find(
    (row) => row.stage_id === data.journey.current_stage)
  return {
    hero: {
      novelId: data.novel.novel_id,
      title: data.novel.title,
      tags,
      premise: data.novel.premise,
      progressPercent: data.progress.percent,
      progressLabel: data.progress.label,
      stageLabel: data.journey.current_stage_label,
      stageProgressLabel: stageProgress
        ? `${stageProgress.progress.done} / ${stageProgress.progress.total} 完成`
        : '',
      continueLabel: data.next_action.action_label,
      visual: entityVisual('hero'),
    },
    stages: data.journey.stages.map(stageViewModel),
    objectives,
    currentObjective,
    nextAction: nextActionViewModel(data.next_action),
    alerts: (data.risks ?? []).map(alertViewModel),
    repair: repairViewModel(data.repair),
    exportView: exportViewModel(data.export),
    content: (data.content ?? []).map(contentViewModel),
    recent: (data.activity ?? []).map(recentViewModel),
    outline: outlineViewModel(data.outline),
    characters: charactersViewModel(data.characters),
    world: worldViewModel(data.world),
    simulation: simulationViewModel(data.simulation),
    facts: {
      creativeBriefSaved: Boolean(data.facts.creative_brief_saved),
      settingSeedSaved: Boolean(data.facts.setting_seed_saved),
      contentPackReady: Boolean(data.facts.content_pack_ready),
      settingsCheckOk: Boolean(data.facts.settings_check_ok),
      runtimeStarted: Boolean(data.facts.runtime_started),
    },
    isEmptyProject: data.progress.done === 0,
    currentStageId: data.journey.current_stage,
  }
}

export function landingCardViewModel(card: NovelCardDto): LandingCardViewModel {
  return {
    novelId: card.novel_id,
    title: card.title,
    tags: [card.genre, ...(card.themes ?? [])].filter(Boolean).slice(0, 3),
    stageLabel: card.stage_label,
    progressPercent: card.progress_percent,
    progressLabel: '总体进度',
    nextAction: card.next_action,
    updatedLabel: relativeTime(card.updated_at),
    stageIcon: STAGE_ICON_FALLBACK[card.stage_id] ?? 'current',
    visual: entityVisual('novel'),
  }
}
