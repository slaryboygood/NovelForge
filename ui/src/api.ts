export interface StoryBuilderStep {
  step: string
  title: string
  prompt: string
  selection_mode: 'single' | 'multiple'
  min_selections: number
  max_selections: number
  skippable: boolean
}

export interface StoryBuilderOption {
  id: string
  step: string
  name: string
  summary: string
  tags: string[]
  effects: Record<string, string>
}

export interface StoryBuilderSelection {
  selection_id: string
  step: string
  option_id?: string | null
  custom_text: string
  source: string
  revision: number
  display_name?: string
}

export interface StoryBuilderSessionPayload {
  design_tree: DesignNode[]
  novel?: {
    novel_id: string
    title: string
    genre: string
    themes: string[]
  }
  session: {
    session_id: string
    project_id: string
    status: string
    current_step: string
    completed_steps: string[]
    needs_review_steps: string[]
    selection_version: number
    recommendation_version: number
  }
  current_step: StoryBuilderStep
  selected: StoryBuilderSelection[]
}

export interface StoryBuilderCatalog {
  language: string
  steps: StoryBuilderStep[]
  options: StoryBuilderOption[]
}

export interface StoryBuilderRecommendation {
  option_id?: string | null
  custom_text: string
  reason: string
  fit_tags: string[]
  risks: string[]
  source: 'rule' | 'ai'
  rank: number
}

export interface StoryBuilderRecommendationPayload {
  session: StoryBuilderSessionPayload['session']
  recommendation: {
    step: string
    based_on_version: number
    recommendations: StoryBuilderRecommendation[]
    conflicts: { code: string; message: string; option_ids: string[]; blocking: boolean }[]
    unlocked_steps: string[]
    can_continue: boolean
  }
}

export interface StoryBlueprintPayload {
  blueprint: {
    design_summaries?: Record<string, string>
    blueprint_id: string
    project_id: string
    source_session_id: string
    source_selection_version: number
    version: number
    status: 'DRAFT' | 'CONFIRMED' | 'SUPERSEDED'
    premise: string
    sections: {
      step: string
      summary: string
      selected_option_ids: string[]
      custom_inputs: string[]
      source_selection_ids: string[]
    }[]
    unresolved_conflicts: { code: string; message: string; option_ids: string[]; blocking: boolean }[]
    confirmed_by_author: boolean
  }
}

export interface StoryOutlinePackage {
  route_source?: Record<string, string>
  route_history?: { scene: string; choice: string; result: string }[]
  design_sections?: Record<string, string>
  pending_questions?: string[]
  package_id: string
  project_id: string
  blueprint_id: string
  blueprint_version: number
  level: 'BOOK' | 'VOLUME' | 'ARC' | 'CHAPTER'
  status: 'DRAFT' | 'REVIEW' | 'NEEDS_REVIEW' | 'CONFIRMED' | 'SUPERSEDED'
  version: number
  parent_package_id?: string | null
  items: {
    pov?: string
    time?: string
    location?: string
    participants?: string[]
    information_changes?: string[]
    costs?: string[]
    item_id: string
    title: string
    summary: string
    start_state: string
    end_state: string
    goals: string[]
    conflicts: string[]
    major_turns: string[]
    ending_hook: string
    must_keep: string[]
    must_avoid: string[]
    child_ids: string[]
  }[]
  source_package_versions: Record<string, number>
  confirmed_by_author: boolean
}

export interface CreatorWorldPayload {
  meta: {
    novel_id: string
    title: string
    content_pack_id: string
    content_pack_title: string
    blueprint_id: string
    blueprint_version: number
    branch_id: string
    persisted: boolean
    preview: boolean
    pack_error: string
  }
  timeline: { tick: number; current_time: string; elapsed: string; markers: string[]; world_ticks: number }
  location: {
    current: string
    name: string
    kind: string
    access: string
    control: string
    danger: number | null
    status: string
    visited: string[]
    visited_labels: string[]
    known: {
      id: string; name: string; kind: string; tags: string[]; access: string
      control: string; danger: number | null; current: boolean; visited: boolean
      data: Record<string, unknown>
    }[]
  }
  factions: {
    id: string; name: string; kind: string; tags: string[]; stance: string
    influence: number | null; resources: unknown; internal_conflicts: unknown
    active_plots: string[]; data: Record<string, unknown>
  }[]
  recent_world_events: {
    event_id: string; title: string; kind: string; scope: string; order: number
    tick: number; source: string; actor: string; actor_label: string
    occurrences: number; knowledge_id: string
  }[]
  recent_autonomous_actions: {
    order: number; tick: number; actor_id: string; actor_label: string; actor_kind: string
    action_id: string; action_label: string; source: string; reason: string
  }[]
  available_events: { event_id: string; title: string; kind: string; scope: string; priority: number; source: string }[]
  active_plots: {
    id: string; title: string; status: string; progress: number; priority: number
    characters: string[]; factions: string[]; locations: string[]; updated_tick: number
  }[]
  world_flags: Record<string, unknown>
  resources: { id: string; amount: number; unit: string; holders: string[] }[]
  event_records: { id: string; status: string; source: string; participants: string[]; title: string }[]
  last_change: { op: string; entity: string; target: string; source: string; order: number; tick: number } | null
}

export interface CreatorCharacterPayload {
  meta: CreatorWorldPayload['meta']
  characters: {
    id: string; name: string; kind: string; status: string; tags: string[]
    is_player: boolean; active_goals: number; memories: number
  }[]
  selected: string
  detail: {
    id: string; name: string; kind: string; status: string; tags: string[]; exists: boolean
    current_goal: CreatorGoal | null
    goals: { long_term: CreatorGoal[]; stage: CreatorGoal[]; current: CreatorGoal[]; active: CreatorGoal[] }
    memories: { id: string; summary: string; source: string; tick: number; participants: string[]; emotion: string[] }[]
    relationships: {
      other_id: string; other_label: string; direction: string
      dimensions: Record<string, number>; tags: string[]; stage: string; data: Record<string, unknown>
    }[]
    arc: { character_id: string; stage: string; stage_id: string; outcome: string; is_forced: boolean; note: string } | null
    knowledge: { id: string; certainty: string; source: string; tick: number; reader_visible: boolean }[]
    drives: {
      goal: string; desire: string; fear: string
      personality: string[]; bottom_line: string[]; current_pressure: string
    }
    recent_actions: { kind: string; order: number; target: string; label: string; source: string; reason: string; tick: number }[]
    reactions: { action_id: string; name: string; kind: string; score: number; reason: string; source: string }[]
  } | null
}

export interface CreatorGoal {
  id: string; scope: string; title: string; description: string
  priority: number; weight: number; score: number; status: string; source: string
  updated_tick: number; has_condition: boolean; note: string
}

export interface CreatorPlotPayload {
  meta: CreatorWorldPayload['meta']
  actor: string
  candidates: {
    action_id: string; name: string; kind: string; available: boolean; code: string; reason: string
    requirements: Record<string, unknown>[]; costs: Record<string, unknown>[]; risks: string[]
    visibility: string; related_characters: string[]; goal_notes: string[]; memory_notes: string[]
    sort_key: number
  }[]
  available: string[]
  unavailable: string[]
  current_events: {
    event_id: string; title: string; kind: string; scope: string; priority: number; status: string
    scene_goal: string; conflict: string; participants: string[]; available_actions: string[]
    followups: string[]; occurrences: number; last_order: number
  }[]
  event_chain: {
    order: number; event_id: string; title: string; scope: string
    actor: string; source: string; followups: string[]
  }[]
  plots: CreatorPlotTrack[]
  active_plots: CreatorPlotTrack[]
  resolved_plots: CreatorPlotTrack[]
  timeline: { tick: number; current_time: string }
  last_world_change: { op: string; entity: string; target: string; source: string; order: number; label: string } | null
  world_impacts: {
    key: string; ops: string[]; actions: string[]; available_actions: string[]
    unavailable_actions: string[]; cost_actions: string[]; blocked_by_this_key: string[]
    impacts_availability: boolean
  }[]
  world_flags: { key: string; value: unknown; referenced_by: string[]; impacts_availability: boolean }[]
  event_history: { order: number; op: string; target: string; title: string; source: string }[]
  triggerable_events: {
    event_id: string; available: boolean; priority: number; code: string; reason: string
    title: string; scope: string
  }[]
}

export interface CreatorPlotTrack {
  id: string; title: string; status: string; progress: number; priority: number
  characters: string[]; factions: string[]; locations: string[]; foreshadows: string[]
  updated_tick: number; source: string; has_trigger: boolean
}

export interface CreatorProgressionNode {
  id: string; tree_id: string; name: string; summary: string; category: string; kind: string
  level: number; tags: string[]; source: string; status: 'owned' | 'available' | 'locked'
  requires: string[]; missing_requires: string[]; exclusive_group: string; blocked_by: string
  reason: string; unlock_condition: Record<string, unknown> | null
  costs: Record<string, unknown>[]; effects: Record<string, unknown>[]
  recommendation: string; story_impact: string; data: Record<string, unknown>
}

export interface CreatorProgressionPayload {
  meta: CreatorWorldPayload['meta']
  actor: string
  trees: { tree_id: string; name: string; nodes: CreatorProgressionNode[]; counts: Record<string, number> }[]
  categories: { category: string; label: string; nodes: CreatorProgressionNode[] }[]
  counts: Record<string, number>
  owned: string[]
  note: string
}

export interface CreatorMemoryPayload {
  meta: CreatorWorldPayload['meta']
  characters: string[]
  author: {
    entries: CreatorKnowledgeRow[]
    author_only: string[]
  }
  reader: { entries: CreatorKnowledgeRow[] }
  character_knowledge: Record<string, CreatorKnowledgeRow[]>
  knowledge_index: CreatorKnowledgeRow[]
  holders: Record<string, string[]>
  reader_only: Record<string, string[]>
  obligations: {
    all: CreatorObligation[]
    by_kind: Record<string, CreatorObligation[]>
    outstanding: CreatorObligation[]
    overdue: CreatorObligation[]
  }
  hostility: {
    source_id: string; target_id: string; hostility: number
    sources: { order: number; delta: number; source: string; reason: string; tick: number }[]
    latest_reason: string; latest_tick: number
  }[]
  conflicts: { kind: string; id: string; title: string; participants: string[]; pressure: number; status: string; source: string; tick: number }[]
  conflicts_by_kind: Record<string, CreatorMemoryPayload['conflicts']>
  foreshadows: CreatorForeshadow[]
  open_foreshadows: CreatorForeshadow[]
  counts: Record<string, number>
}

export interface CreatorKnowledgeRow {
  id: string; certainty: string; holders: string[]; source: string
  source_event: string; tick: number; reader_visible: boolean
}

export interface CreatorObligation {
  id: string; kind: string; debtor: string; creditor: string; description: string
  status: string; source: string; created_tick: number; due_tick: number
  settled_tick: number; overdue: boolean; note: string
}

export interface CreatorForeshadow {
  id: string; title: string; status: string; planted_in: string; payoff_in: string
  has_payoff_condition: boolean; payoff_ready: boolean; payoff_reason: string
  transformed_into: string; author_note: string; planted_tick: number
}

export interface CreatorDirectorPayload {
  meta: CreatorWorldPayload['meta']
  actor: string
  /** 只有存在已发生事实（StoryState 有选择记录）时后端才返回这些字段。 */
  last_choice?: string
  weights: Record<string, number>
  weights_config: Record<string, number>
  weights_keys?: string[]
  available_events: { event_id: string; available: boolean; priority: number; code: string; reason: string }[]
  scored?: { event_id: string; score: number; dimensions: Record<string, number>; reasons: string[]; deductions: string[] }[]
  ranked: {
    event_id: string; title: string; kind: string; scope: string; priority: number
    score: number; dimensions: Record<string, number>; reasons: string[]; deductions: string[]
    is_chosen: boolean
  }[]
  chosen: string
  chosen_title: string
  why_chosen: string[]
  why_not: Record<string, string[]>
  note: string
}

export interface CreatorLinkagePayload {
  meta: CreatorWorldPayload['meta']
  story_state: {
    tick: number; current_time: string; current_location: string
    effect_log: number; plots: number; active_events: number
  }
  route: {
    happened: CreatorRouteRecord[]
    planned: CreatorRouteRecord[]
    suggested: CreatorRouteRecord[]
  }
  counts: { happened: number; planned: number; suggested: number }
  long_line: {
    volumes: { id: string; arcs: string[]; sources: string[] }[]
    arcs: { id: string; chapters: string[]; sources: string[] }[]
    chapters: { id: string; title: string; source: string; origin: string; tick: number }[]
    unresolved: string[]
  }
  outline_preview: {
    item_id: string; title: string; summary: string; start_state: string; end_state: string
    goals: string[]; conflicts: string[]; major_turns: string[]; must_keep: string[]
    must_avoid: string[]; child_ids: string[]; pov: string; time: string; location: string
    participants: string[]; information_changes: string[]; costs: string[]; ending_hook: string
  }[]
  trace: { verified: string[]; unsourced: { item_id: string; mark: string; reason: string }[] }
  unresolved: string[]
  plans: { id: string; title: string; goal: string; status: string; note: string }[]
  existing_outlines: {
    package_id: string; level: string; status: string; version: number
    parent_package_id: string | null
    items: { item_id: string; title: string; summary: string }[]
    pending_questions: string[]; route_source: Record<string, string>; blueprint_version: number
  }[]
  history_immutable: boolean
  replan_preview?: {
    changed_stage: string; note: string
    plan: { id: string; title: string; goal: string; status: string; note: string }[]
    plan_revision: number; happened_unchanged: boolean
    planned: CreatorRouteRecord[]; suggested: CreatorRouteRecord[]
  }
}

export interface CreatorRouteRecord {
  id: string; kind: string; origin: string; source: string; tick: number
  participants: string[]; location: string; result: string; data: Record<string, unknown>
}

export interface CreativeGenreCandidate {
  genre: string; label: string; template_id: string; content_pack_id: string; reason: string
}

export interface CreativeToneCandidate { tone: string; reason: string }
export interface CreativeSellingPoint { text: string; reason: string }

export interface CreativeBrief {
  original_idea: string
  references: string[]
  reader_experience: string
  selected_genre: string
  selected_template_id: string
  selected_content_pack_id: string
  tone: string
  selling_points: string[]
}

export interface CreativeSuggestionPayload {
  novel_id: string
  original_idea: string
  references: string[]
  reader_experience: string
  genre_candidates: CreativeGenreCandidate[]
  tone_candidates: CreativeToneCandidate[]
  selling_point_candidates: CreativeSellingPoint[]
  selection: CreativeBrief
  source: string
  notes: string[]
}

export interface CreativeBriefState {
  novel_id: string
  brief: CreativeBrief | null
  suggestion: CreativeSuggestionPayload | null
}

export interface SettingCandidate {
  id: string
  label: string
  summary: string
  reason: string
  data: Record<string, unknown>
}

export interface SettingSeed {
  novel_id: string
  original_idea: string
  genre: string
  tone: string
  selling_points: string[]
  world_rules: SettingCandidate[]
  protagonist: SettingCandidate[]
  characters: SettingCandidate[]
  factions: SettingCandidate[]
  relationships: SettingCandidate[]
  progression: SettingCandidate[]
  conflicts: SettingCandidate[]
  main_line: SettingCandidate[]
  foreshadows: SettingCandidate[]
  selected: Record<string, string[]>
  source: string
  notes: string[]
}

export interface SettingSeedState {
  novel_id: string
  seed: SettingSeed | null
  pack_id: string
  pack: Record<string, unknown> | null
  groups: string[]
  saved: boolean
}

export interface SettingSeedSuggestion {
  novel_id: string
  seed: SettingSeed
  pack_id: string
  pack_preview: Record<string, unknown>
  groups: string[]
}

export interface SettingsCheckFinding {
  code: string
  severity: 'error' | 'warning'
  message: string
  hint: string
  target: string
}

export interface GuidedFlowStep {
  step_id: string
  title: string
  stage: 'design' | 'occurred' | 'output'
  stage_label: string
  detail: string
  status: 'done' | 'current' | 'pending' | 'blocked'
  deep_link: { panel: string; step: string; group: string; hash: string }
}

export interface GuidedFlowState {
  novel_id: string
  current_stage: string
  current_stage_label: string
  current_step: string
  next_step: GuidedFlowStep | null
  steps: GuidedFlowStep[]
  context: { novel_id: string; pack_id: string; branch_id: string }
  facts: {
    creative_brief_saved: boolean
    setting_seed_saved: boolean
    content_pack_ready: boolean
    settings_check_ok: boolean
    settings_check_findings: SettingsCheckFinding[]
    settings_check_error: string
    runtime_started: boolean
    runtime_error: string
  }
  fact_layers: Record<string, string>
  read_only: boolean
}

export interface SettingImpactCandidate {
  id: string
  label: string
  summary: string
  reason: string
  selected: boolean
  impact: { profile_fields: string[]; pack_sections: string[]; unlock_action_ids: string[] }
}

export interface SettingImpactGroup {
  group: string
  label: string
  profile_fields: string[]
  pack_sections: string[]
  unlock_ops: string[]
  selected_ids: string[]
  candidates: SettingImpactCandidate[]
  section_presence: Record<string, boolean>
  unlocks: Array<{ action_id: string; name: string; requirement_ops: string[]; matched_ops: string[] }>
}

export interface SettingImpactPayload {
  novel_id: string
  pack_id: string
  pack_ready: boolean
  groups: SettingImpactGroup[]
  finding_groups: Record<string, string>
  fact_layers: Record<string, string>
  note: string
  read_only: boolean
}

export interface OverviewCardItem {
  id: string; label: string; summary: string; reason: string; selected: boolean
  core_companion?: boolean
}

export interface SettingOverviewPayload {
  novel_id: string
  pack_id: string
  cards: Array<{
    card_id: string; title: string; truth_layer: string; source_group: string
    items: OverviewCardItem[]; item_count: number; note: string
  }>
  fact_layers: Record<string, string>
  read_only: boolean
}

export interface RegionCard {
  region_id: string; name: string; kind: string; explored: boolean; current: boolean
  truth_layer: string; danger: number | null; danger_label: string
  known_resources: string[]; known_information: string[]; entry_conditions: string[]
}

export interface RegionCardsPayload {
  novel_id: string; branch_id: string; current_location: string
  regions: RegionCard[]; region_fields: string[]; visited: string[]
  unknown_count: number; fact_layers: Record<string, string>; read_only: boolean
}

export interface RelationshipGraphPayload {
  novel_id: string; selected: string
  nodes: Array<{ node_id: string; label: string; kind: string; status: string
    tags: string[]; truth_layer: string }>
  edges: Array<{ source: string; source_label: string; target: string
    target_label: string; direction: string; dimensions: Record<string, number>
    tags: string[]; stage: string; truth_layer: string
    change_records: Array<{ order: number; delta: number; source: string
      reason: string; tick: number }> }>
  fact_layers: Record<string, string>; read_only: boolean
}

export interface InspectorRow {
  record_kind: string; ref_id: string; label: string; summary?: string
  truth_layer: string; status?: string; source_refs?: string[]
}

export interface InspectorOverviewPayload {
  novel_id: string
  canon: { available: boolean; fact_count: number; entity_count: number; db_ref: string }
  story_state: { available: boolean; record_count: number; records: InspectorRow[] }
  chapter_ir: { chapter_count: number; index_digest: string; index_ref: string }
  layers: string[]; read_only: boolean
}

export interface InspectorSearchPayload {
  novel_id: string; query: string; layer: string; record_kind: string
  total: number; rows: InspectorRow[]; kinds: string[]; layers: string[]
  read_only: boolean
}

export interface InspectorRecordPayload {
  novel_id: string; ref_id: string; found: boolean; note?: string
  record?: InspectorRow
  provenance?: Array<{ ref: string; kind: string }>
  truth_layer?: string; read_only: boolean
}

export interface RepairIssue {
  issue_id: string; source: string; severity: string; message: string; hint: string
  target: string; proposed_action: string; execution_api: string
  requires_approval: boolean; approval_note: string
  impact: Record<string, unknown>; truth_layer: string; evidence: string[]
}

export interface RepairDiagnosisPayload {
  novel_id: string; issue_count: number; issues: RepairIssue[]
  outline_quality_ok?: boolean | null; execution_boundary: string; read_only: boolean
}

export interface RepairHistoryPayload {
  novel_id: string
  effect_log: Array<{ order: number; op: string; target: string; source: string
    truth_layer: string }>
  outline_versions_ref: string
  read_only: boolean
}

export interface SettingsCheckReport {
  novel_id: string
  pack_id: string
  ok: boolean
  repairable: boolean
  findings: SettingsCheckFinding[]
  applied_fixes: string[]
  repaired?: boolean
  story_state: Record<string, unknown>
  available_candidates: string[]
  blocked_candidates: Array<{ action: string; code: string; reason: string }>
}

export interface RuntimeCandidateRow {
  action_id: string
  name: string
  kind: string
  available: boolean
  code: string
  reason: string
}

export interface RuntimeStartPayload {
  revision: number
  tick: number
  summary: Record<string, unknown>
  candidates: RuntimeCandidateRow[]
  available: string[]
  blocked: string[]
  started: boolean
  created: boolean
  runtime_id: string
  branch_id: string
  meta: Record<string, unknown>
}

/**
 * runtime/advance 的真实返回（引擎 AdvanceResult 的去 state 摘要）。
 * 用途：V3 推演反馈闭环——作者必须知道「故事发生了什么」，而不是只看到 200 OK。
 */
export interface AdvanceResultPayload {
  ok: boolean
  blocked: string
  terminal: boolean
  revision: number
  tick: number
  executed_action: string
  outcome: string
  code: string
  message: string
  effects: Record<string, unknown>[]
  settled_delayed: string[]
  delayed_failures: Record<string, unknown>[]
  world_actions: Record<string, unknown>[]
  world_events: string[]
  triggered_events: string[]
  director_decision: Record<string, unknown>
  writer_result: Record<string, unknown>
  current_state_summary: Record<string, unknown>
  next_candidates: RuntimeCandidateRow[]
  available_actions: string[]
  diagnostics: Record<string, unknown>[]
  plot_transitions: Record<string, unknown>[]
  future_plan_changed: boolean
  replan_reason: string
  branch_id: string
  meta: Record<string, unknown>
}

export interface BranchRowPayload {
  branch_id: string
  revision: number
  tick: number
  location: string
  characters: number
  knowledge: number
  plots_active: number
  foreshadows_open: number
  official: boolean
  frozen_revision: number
  source_branch: string
}

export interface BranchListPayload {
  novel_id: string
  runtime_id: string
  official_branch: string
  frozen_revision: number
  started: boolean
  branches: BranchRowPayload[]
}

export interface BranchDiffRow {
  kind: string
  item_id: string
  label: string
  base: unknown
  target: unknown
  mergeable: boolean
  conflict: boolean
  note: string
  effect: Record<string, unknown> | null
}

export interface BranchComparisonPayload {
  novel_id: string
  base_branch: string
  target_branch: string
  base_revision: number
  target_revision: number
  rows: BranchDiffRow[]
  summary: string[]
  conflicts: string[]
}

export interface BranchMergePreviewPayload {
  novel_id: string
  target_branch: string
  sources: Array<{
    source_branch: string
    mergeable: Array<{ kind: string; item: string; label: string; note: string }>
    conflicts: Array<{ kind: string; item: string; label: string; note: string }>
    other: Array<{ kind: string; item: string; label: string; note: string }>
  }>
  note: string
}

export interface BranchMergeResult {
  novel_id: string
  target_branch: string
  merged: Array<{ branch: string; kind: string; item: string; label: string }>
  skipped: Array<{ branch: string; kind: string; item: string; reason: string; note: string }>
  failures: Array<{ branch: string; kind: string; item: string; code: string; message: string }>
  revision: number
  tick: number
  history_preserved: boolean
}

export interface OutlineQualityFinding {
  code: string
  severity: string
  message: string
  target: string
}

export interface OutlineQualityReport {
  novel_id: string
  ok: boolean
  counts: Record<string, number>
  findings: OutlineQualityFinding[]
  pacing: string[]
}

export interface OutlineChapterPlan {
  id: string
  index: number
  volume_index: number
  arc_index: number
  kind: string
  title: string
  summary: string
  goal: string
  conflict: string
  turn: string
  hook: string
  start_state: string
  end_state: string
  location: string
  time: string
  participants: string[]
  information_changes: string[]
  relationship_changes: string[]
  progression_changes: string[]
  plot_changes: string[]
  foreshadow_moves: string[]
  costs: string[]
  source_ids: string[]
  must_keep: string[]
  must_avoid: string[]
}

export interface OutlinePlanPayload {
  novel_id: string
  branch_id: string
  revision: number
  tick: number
  structure: { volumes: number; arcs_per_volume: number; chapters_per_arc: number }
  book_title: string
  book_goal: string
  book_conflict: string
  book_turn: string
  book_end_state: string
  volumes: Array<{ id: string; index: number; title: string; goal: string; conflict: string
    turn: string; arc_ids: string[] }>
  arcs: Array<{ id: string; index: number; volume_id: string; title: string; question: string
    closes_with: string; chapter_ids: string[] }>
  chapters: OutlineChapterPlan[]
  unresolved: Array<{ id: string; kind: string; source: string; result: string }>
  notes: string[]
}

export interface OutlinePlanResponse {
  novel_id: string
  branch_id: string
  plan: OutlinePlanPayload
  quality: OutlineQualityReport
}

export interface OutlinePackagePayload {
  package_id: string
  project_id: string
  blueprint_id: string
  blueprint_version: number
  level: string
  status: string
  version: number
  parent_package_id: string | null
  items: Array<{
    item_id: string; title: string; summary: string; start_state: string; end_state: string
    goals: string[]; conflicts: string[]; major_turns: string[]; ending_hook: string
    must_keep: string[]; must_avoid: string[]; pov: string; time: string; location: string
    participants: string[]; information_changes: string[]; costs: string[]
  }>
  route_source: Record<string, string>
  design_sections: Record<string, string>
  pending_questions: string[]
  confirmed_by_author: boolean
}

export interface OutlineChainPayload {
  novel_id: string
  branch_id: string
  book: OutlinePackagePayload | null
  fresh: boolean
  volumes: OutlinePackagePayload[]
  arcs: OutlinePackagePayload[]
  chapters: OutlinePackagePayload[]
  quality: OutlineQualityReport | null
}

export interface OutlineVersionRow {
  version: number
  status: string
  confirmed_by_author: boolean
  item_count: number
  item_titles: string[]
  route_digest: string
  created_at: string
}

export interface OutlineVersionDiffRow {
  item_id: string
  status: string
  changed_fields: string[]
  before: Record<string, unknown>
  after: Record<string, unknown>
}

export interface OutlineImpactPayload {
  package_id: string
  level: string
  item_id: string
  item_kind: string
  protected_fields: string[]
  affected_downstream: Array<{ package_id: string; level: string; status: string; items: number }>
  affected_happened: Array<{ package_id: string; level: string; item_id: string; title: string }>
  affected_planned: Array<{ package_id: string; level: string; item_id: string; title: string }>
  note: string
}

const BASE = ''

export class ApiError extends Error {
  status: number
  detail: any

  constructor(message: string, status: number, detail: any) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + url, init)
  if (!res.ok) {
    const body = await res.text()
    let payload: any = null
    try { payload = JSON.parse(body) } catch { /* 保留非 JSON 错误 */ }
    const detail = payload?.detail ?? payload
    const message = typeof detail === 'string' ? detail : (detail?.message ?? (body || res.statusText))
    throw new ApiError(message, res.status, detail)
  }
  return res.json() as Promise<T>
}

/** V3 复用的同一套 JSON 请求入口（错误语义与 V2 面板一致，避免第二套客户端）。 */
export { j as requestJson }

export const api = {
  storyBuilderSessions: (projectId: string) =>
    j<{ sessions: { session_id: string; created_at: string; label: string; selection_version: number }[] }>(`/api/story-builder/sessions?project_id=${encodeURIComponent(projectId)}`),
  storyBuilderSession: (id: string) => j<StoryBuilderSessionPayload>(`/api/story-builder/sessions/${encodeURIComponent(id)}`),
  editOutline: (id: string, item: string, expected_version: number, changes: Record<string, unknown>) =>
    j<{ outline: StoryOutlinePackage }>(`/api/story-builder/outlines/${encodeURIComponent(id)}/items/${encodeURIComponent(item)}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_version, changes }),
    }),
  exportOutline: (id: string, version: number) =>
    j<{ filename: string; content: string }>(`/api/story-builder/outlines/${encodeURIComponent(id)}/export?version=${version}`),
  compileRouteOutline: (id: string, version: number, branch_id: string, expected_revision: number) =>
    j<{ outline: StoryOutlinePackage }>(`/api/story-builder/blueprints/${encodeURIComponent(id)}/adventures/${version}/outline`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ branch_id, expected_revision }),
    }),
  adventureAuthorPlan: (id: string, version: number) =>
    j<Record<string, string>>(`/api/story-builder/blueprints/${encodeURIComponent(id)}/adventures/${version}/author-plan`),
  adventureBranches: (id: string, version: number) =>
    j<{ branches: AdventureBranch[] }>(`/api/story-builder/blueprints/${encodeURIComponent(id)}/adventures/${version}/branches`),
  forkAdventure: (id: string, version: number, parent_branch: string, at_revision: number, expected_revision: number, request_id: string) =>
    j<AdventureView>(`/api/story-builder/blueprints/${encodeURIComponent(id)}/adventures/${version}/branches`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ parent_branch, at_revision, expected_revision, request_id }),
    }),
  saveDesign: (sessionId: string, field: string, version: number, option_id?: string, custom_text = '') =>
    j<StoryBuilderSessionPayload>(`/api/story-builder/sessions/${encodeURIComponent(sessionId)}/design/${encodeURIComponent(field)}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_selection_version: version, option_id, custom_text }),
    }),
  adventure: (id: string, version: number, choice?: { revision: number; choice_id: string }, branch = 'main') =>
    j<AdventureView>(`/api/story-builder/blueprints/${encodeURIComponent(id)}/adventures/${version}${branch !== 'main' ? '/branches/' + encodeURIComponent(branch) : ''}${choice ? '/choices' : ''}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: choice ? JSON.stringify(choice) : undefined,
    }),
  storyBuilderCatalog: () => j<StoryBuilderCatalog>('/api/story-builder/catalogs'),
  storyBuilderNovels: () =>
    j<{ novels: { novel_id: string; title: string; genre: string }[] }>('/api/story-builder/novels'),
  storyBuilderContentPacks: () =>
    j<{ packs: { pack_id: string; title: string; genre: string }[] }>('/api/story-builder/content-packs'),
  creatorWorld: (novelId: string) =>
    j<CreatorWorldPayload>(`/api/story-builder/creator/world?novel_id=${encodeURIComponent(novelId)}`),
  creatorCharacters: (novelId: string, characterId = '', reactions = true) =>
    j<CreatorCharacterPayload>(`/api/story-builder/creator/characters?novel_id=${encodeURIComponent(novelId)}&character_id=${encodeURIComponent(characterId)}&reactions=${reactions ? 'true' : 'false'}`),
  creatorPlot: (novelId: string, actor = '') =>
    j<CreatorPlotPayload>(`/api/story-builder/creator/plot?novel_id=${encodeURIComponent(novelId)}&actor=${encodeURIComponent(actor)}`),
  creatorProgression: (novelId: string, category = '') =>
    j<CreatorProgressionPayload>(`/api/story-builder/creator/progression?novel_id=${encodeURIComponent(novelId)}&category=${encodeURIComponent(category)}`),
  creatorMemory: (novelId: string) =>
    j<CreatorMemoryPayload>(`/api/story-builder/creator/memory?novel_id=${encodeURIComponent(novelId)}`),
  creativeBrief: (novelId: string) =>
    j<CreativeBriefState>(`/api/story-builder/creative/brief?novel_id=${encodeURIComponent(novelId)}`),
  creativeSuggest: (novelId: string, body: {
    idea: string; references?: string[]; reader_experience?: string
    selected_genre?: string; regenerate?: boolean
  }) => j<CreativeSuggestionPayload>(`/api/story-builder/creative/suggest?novel_id=${encodeURIComponent(novelId)}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  saveCreativeBrief: (novelId: string, brief: CreativeBrief) =>
    j<{ novel: Record<string, unknown>; brief: CreativeBrief }>(
      `/api/story-builder/creative/brief?novel_id=${encodeURIComponent(novelId)}`,
      { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(brief) }),
  settingSeed: (novelId: string) =>
    j<SettingSeedState>(`/api/story-builder/settings/seed?novel_id=${encodeURIComponent(novelId)}`),
  suggestSettingSeed: (novelId: string, body: { regenerate?: boolean; selected?: Record<string, string[]> }) =>
    j<SettingSeedSuggestion>(`/api/story-builder/settings/seed?novel_id=${encodeURIComponent(novelId)}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }),
  saveSettingSeed: (novelId: string, body: { seed: SettingSeed; selected: Record<string, string[]>; pack_id?: string }) =>
    j<{ novel_id: string; seed: SettingSeed; pack_id: string; pack: Record<string, unknown>; novel: Record<string, unknown>; notes: string[] }>(
      `/api/story-builder/settings/seed?novel_id=${encodeURIComponent(novelId)}`,
      { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  settingsCheck: (novelId: string) =>
    j<SettingsCheckReport>(`/api/story-builder/settings/check?novel_id=${encodeURIComponent(novelId)}`),
  guidedFlow: (novelId: string) =>
    j<GuidedFlowState>(`/api/story-builder/guided-flow?novel_id=${encodeURIComponent(novelId)}`),
  settingsImpact: (novelId: string, group = '') =>
    j<SettingImpactPayload>(`/api/story-builder/settings/impact?novel_id=${encodeURIComponent(novelId)}${group ? '&group=' + encodeURIComponent(group) : ''}`),
  settingsOverview: (novelId: string) =>
    j<SettingOverviewPayload>(`/api/story-builder/settings/overview?novel_id=${encodeURIComponent(novelId)}`),
  settingsRegions: (novelId: string) =>
    j<RegionCardsPayload>(`/api/story-builder/settings/regions?novel_id=${encodeURIComponent(novelId)}`),
  settingsRelationships: (novelId: string, characterId = '') =>
    j<RelationshipGraphPayload>(`/api/story-builder/settings/relationships?novel_id=${encodeURIComponent(novelId)}&character_id=${encodeURIComponent(characterId)}`),
  inspectorOverview: (novelId: string) =>
    j<InspectorOverviewPayload>(`/api/story-builder/inspector/overview?novel_id=${encodeURIComponent(novelId)}`),
  inspectorSearch: (novelId: string, query: { query?: string; layer?: string; record_kind?: string; limit?: number } = {}) =>
    j<InspectorSearchPayload>(`/api/story-builder/inspector/search?novel_id=${encodeURIComponent(novelId)}`
      + `&query=${encodeURIComponent(query.query ?? '')}&layer=${encodeURIComponent(query.layer ?? '')}`
      + `&record_kind=${encodeURIComponent(query.record_kind ?? '')}&limit=${query.limit ?? 50}`),
  inspectorRecord: (novelId: string, refId: string) =>
    j<InspectorRecordPayload>(`/api/story-builder/inspector/record?novel_id=${encodeURIComponent(novelId)}&ref_id=${encodeURIComponent(refId)}`),
  repairDiagnosis: (novelId: string) =>
    j<RepairDiagnosisPayload>(`/api/story-builder/repair/diagnosis?novel_id=${encodeURIComponent(novelId)}`),
  repairHistory: (novelId: string) =>
    j<RepairHistoryPayload>(`/api/story-builder/repair/history?novel_id=${encodeURIComponent(novelId)}`),
  runSettingsCheck: (novelId: string, body: { repair?: boolean; seed?: SettingSeed }) =>
    j<SettingsCheckReport>(`/api/story-builder/settings/check?novel_id=${encodeURIComponent(novelId)}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }),
  startRuntime: (novelId: string, body: { branch_id?: string } = {}) =>
    j<RuntimeStartPayload>(`/api/story-builder/runtime/start?novel_id=${encodeURIComponent(novelId)}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }),
  runtimeState: (novelId: string, branchId = 'main') =>
    j<RuntimeStartPayload & { started: boolean }>(
      `/api/story-builder/runtime/state?novel_id=${encodeURIComponent(novelId)}&branch_id=${encodeURIComponent(branchId)}`),
  advanceRuntime: (novelId: string, body: { action_id: string; branch_id: string
    expected_revision?: number }) =>
    j<AdvanceResultPayload>(`/api/story-builder/runtime/advance?novel_id=${encodeURIComponent(novelId)}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }),
  runtimeBranches: (novelId: string) =>
    j<BranchListPayload>(`/api/story-builder/runtime/branches?novel_id=${encodeURIComponent(novelId)}`),
  forkBranch: (novelId: string, body: { source_branch: string; label?: string }) =>
    j<{ branch_id: string; source_branch: string; revision: number; tick: number }>(
      `/api/story-builder/runtime/branches/fork?novel_id=${encodeURIComponent(novelId)}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  compareBranches: (novelId: string, baseBranch: string, targetBranch: string) =>
    j<BranchComparisonPayload>(
      `/api/story-builder/runtime/branches/compare?novel_id=${encodeURIComponent(novelId)}`
      + `&base_branch=${encodeURIComponent(baseBranch)}&target_branch=${encodeURIComponent(targetBranch)}`),
  previewBranchMerge: (novelId: string, body: { target_branch: string; source_branches: string[] }) =>
    j<BranchMergePreviewPayload>(
      `/api/story-builder/runtime/branches/merge/preview?novel_id=${encodeURIComponent(novelId)}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  mergeBranches: (novelId: string, body: { target_branch: string; source_branches: string[]
    item_keys: string[] }) =>
    j<BranchMergeResult>(`/api/story-builder/runtime/branches/merge?novel_id=${encodeURIComponent(novelId)}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  freezeBranch: (novelId: string, body: { branch_id: string; label?: string }) =>
    j<{ official_branch: string; frozen_branch: string; frozen_revision: number }>(
      `/api/story-builder/runtime/branches/freeze?novel_id=${encodeURIComponent(novelId)}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  outlinePlan: (novelId: string, query: { branch_id?: string; volumes: number
    arcs_per_volume: number; chapters_per_arc: number }) =>
    j<OutlinePlanResponse>(`/api/story-builder/outline/plan?novel_id=${encodeURIComponent(novelId)}`
      + `&branch_id=${encodeURIComponent(query.branch_id ?? 'main')}`
      + `&volumes=${query.volumes}&arcs_per_volume=${query.arcs_per_volume}`
      + `&chapters_per_arc=${query.chapters_per_arc}`),
  forgeOutline: (novelId: string, body: { branch_id?: string; volumes: number
    arcs_per_volume: number; chapters_per_arc: number; expected_revision?: number }) =>
    j<{ novel_id: string; branch_id: string; plan: OutlinePlanPayload
      quality: OutlineQualityReport; package_ids: Record<string, string>
      counts: Record<string, number> }>(
      `/api/story-builder/outline/forge?novel_id=${encodeURIComponent(novelId)}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  outlineChain: (novelId: string, branchId = 'main') =>
    j<OutlineChainPayload>(
      `/api/story-builder/outline/chain?novel_id=${encodeURIComponent(novelId)}&branch_id=${encodeURIComponent(branchId)}`),
  confirmOutlineChain: (novelId: string, branchId = 'main') =>
    j<{ novel_id: string; branch_id: string; count: number
      confirmed: Array<{ package_id: string; level: string; version: number }> }>(
      `/api/story-builder/outline/confirm?novel_id=${encodeURIComponent(novelId)}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ branch_id: branchId }) }),
  outlineExport: (novelId: string, branchId = 'main') =>
    j<{ filename: string; content: string }>(
      `/api/story-builder/outline/export?novel_id=${encodeURIComponent(novelId)}&branch_id=${encodeURIComponent(branchId)}`),
  outlineVersions: (novelId: string, packageId: string) =>
    j<{ package_id: string; level: string; versions: OutlineVersionRow[] }>(
      `/api/story-builder/outline/versions?novel_id=${encodeURIComponent(novelId)}`
      + `&package_id=${encodeURIComponent(packageId)}`),
  outlineVersionDiff: (novelId: string, packageId: string, fromVersion: number,
    toVersion: number) =>
    j<{ package_id: string; level: string; from_version: number; to_version: number
      items: OutlineVersionDiffRow[]; added: string[]; removed: string[] }>(
      `/api/story-builder/outline/version-diff?novel_id=${encodeURIComponent(novelId)}`
      + `&package_id=${encodeURIComponent(packageId)}&from_version=${fromVersion}`
      + `&to_version=${toVersion}`),
  outlineImpact: (novelId: string, packageId: string, itemId: string, branchId = 'main') =>
    j<OutlineImpactPayload>(
      `/api/story-builder/outline/impact?novel_id=${encodeURIComponent(novelId)}`
      + `&branch_id=${encodeURIComponent(branchId)}&package_id=${encodeURIComponent(packageId)}`
      + `&item_id=${encodeURIComponent(itemId)}`),
  reviseOutlineItem: (novelId: string, body: { package_id: string; item_id: string
    expected_version: number; changes: Record<string, unknown>; branch_id?: string }) =>
    j<{ outline: OutlinePackagePayload; impact: OutlineImpactPayload }>(
      `/api/story-builder/outline/revise?novel_id=${encodeURIComponent(novelId)}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  restoreOutlineVersion: (novelId: string, body: { package_id: string; version: number }) =>
    j<{ outline: OutlinePackagePayload; restored_from: number }>(
      `/api/story-builder/outline/restore?novel_id=${encodeURIComponent(novelId)}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  mergeOutlineVersions: (novelId: string, body: { package_id: string; base_version: number
    source_version: number; item_ids: string[] }) =>
    j<{ outline: OutlinePackagePayload; merged_items: string[] }>(
      `/api/story-builder/outline/merge-versions?novel_id=${encodeURIComponent(novelId)}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  outlineExportFormat: (novelId: string, format: 'markdown' | 'json' | 'docx',
    branchId = 'main') =>
    j<{ filename: string; format: string; content?: string; content_base64?: string; size?: number }>(
      `/api/story-builder/outline/export?novel_id=${encodeURIComponent(novelId)}`
      + `&branch_id=${encodeURIComponent(branchId)}&format=${format}`),
  creatorDirector: (novelId: string, actor = '') =>
    j<CreatorDirectorPayload>(`/api/story-builder/creator/director?novel_id=${encodeURIComponent(novelId)}&actor=${encodeURIComponent(actor)}`),
  updateDirectorWeights: (novelId: string, weights: Record<string, number>) =>
    j<{ novel: Record<string, unknown>; director: CreatorDirectorPayload }>(
      `/api/story-builder/creator/director/weights?novel_id=${encodeURIComponent(novelId)}`,
      { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ weights }) }),
  creatorLinkage: (novelId: string, preview = false, changedStage = '', note = '') =>
    j<CreatorLinkagePayload>(`/api/story-builder/creator/linkage?novel_id=${encodeURIComponent(novelId)}&preview=${preview ? 'true' : 'false'}&changed_stage=${encodeURIComponent(changedStage)}&note=${encodeURIComponent(note)}`),
  storyBuilderCreateNovel: (novel_id: string, title: string, content_pack_id: string) =>
    j<{ novel: { novel_id: string; title: string; content_pack_id: string } }>('/api/story-builder/novels', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ novel_id, title, content_pack_id }),
    }),
  storyBuilderStep: (step: string) =>
    j<{ step: StoryBuilderStep; options: StoryBuilderOption[] }>(`/api/story-builder/steps/${encodeURIComponent(step)}`),
  storyBuilderLatest: (projectId: string) =>
    j<StoryBuilderSessionPayload>(`/api/story-builder/sessions/latest?project_id=${encodeURIComponent(projectId)}`),
  storyBuilderCreate: (projectId: string, entryStep = 'reader_experience') =>
    j<StoryBuilderSessionPayload>('/api/story-builder/sessions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: projectId, entry_step: entryStep }),
    }),
  storyBuilderRecommend: (sessionId: string, step?: string) =>
    j<StoryBuilderRecommendationPayload>(`/api/story-builder/sessions/${encodeURIComponent(sessionId)}/recommendations`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(step ? { step } : {}),
    }),
  storyBuilderSelect: (sessionId: string, body: {
    step: string; option_ids: string[]; custom_texts: string[]; expected_selection_version: number; option_source?: string
  }) => j<StoryBuilderSessionPayload>(`/api/story-builder/sessions/${encodeURIComponent(sessionId)}/selections`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  storyBuilderBack: (sessionId: string, targetStep: string, expectedVersion: number) =>
    j<StoryBuilderSessionPayload>(`/api/story-builder/sessions/${encodeURIComponent(sessionId)}/back`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_step: targetStep, expected_selection_version: expectedVersion }),
    }),
  storyBuilderBlueprint: (sessionId: string) =>
    j<StoryBlueprintPayload>(`/api/story-builder/sessions/${encodeURIComponent(sessionId)}/blueprint`),
  storyBuilderCompileBlueprint: (sessionId: string) =>
    j<StoryBlueprintPayload>(`/api/story-builder/sessions/${encodeURIComponent(sessionId)}/compile-blueprint`, { method: 'POST' }),
  storyBuilderConfirmBlueprint: (blueprintId: string, version: number) =>
    j<StoryBlueprintPayload>(`/api/story-builder/blueprints/${encodeURIComponent(blueprintId)}/confirm`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version }),
    }),
  storyBuilderOutlines: (blueprintId: string) =>
    j<{ outlines: StoryOutlinePackage[] }>(`/api/story-builder/blueprints/${encodeURIComponent(blueprintId)}/outlines`),
  storyBuilderCompileOutline: (blueprintId: string, level: StoryOutlinePackage['level'], blueprintVersion: number, regenerate = false) =>
    j<{ outline: StoryOutlinePackage }>(`/api/story-builder/blueprints/${encodeURIComponent(blueprintId)}/outlines/${level}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ blueprint_version: blueprintVersion, regenerate }),
    }),
  storyBuilderConfirmOutline: (packageId: string, version: number) =>
    j<{ outline: StoryOutlinePackage }>(`/api/story-builder/outlines/${encodeURIComponent(packageId)}/confirm`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version }),
    }),
}

export type AdventureView = {
  title: string; text: string; completed: boolean;
  warnings?: string[];
  choices: { id: string; label: string; cost: string; suggested?: boolean }[];
  state: { branch_id: string; rules_version: number; revision: number; supplies: number; ally: boolean; clue: boolean; trust?: number; debt?: number; facts?: string[];
    history: { scene: string; choice: string; result: string }[] };
}

export type AdventureBranch = { branch_id: string; revision: number; parent_branch: string | null; fork_revision: number | null }

export type DesignNode = {
  id: string; step: string; title: string; prompt: string; unlocked: boolean; needs_review: boolean; reason: string;
  selection: { option_id: string | null; custom_text: string } | null;
  options: { id: string; name: string; summary: string; available: boolean; reason: string; recommendation: string; effects: Record<string, string>; examples: string[] }[];
}
