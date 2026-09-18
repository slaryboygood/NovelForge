/*
 * Blueprint 节点类型 → 作者语言（标题 / 图标 / 字段标签）。
 * 只做「翻译」，不做业务判断；未知字段回退为原始 key（不隐藏数据）。
 */

export interface FieldSpec {
  key: string
  label: string
  multiline?: boolean
  list?: boolean
}

export interface NodeTypeSpec {
  label: string
  icon: string
  /** 卡片主字段（按作者阅读顺序）。 */
  cardFields: string[]
  fields: FieldSpec[]
}

const F = (key: string, label: string, extra: Partial<FieldSpec> = {}): FieldSpec =>
  ({ key, label, ...extra })

export const NODE_TYPE_SPECS: Record<string, NodeTypeSpec> = {
  premise: {
    label: '前提', icon: 'creation',
    cardFields: ['premise', 'central_conflict', 'dramatic_question'],
    fields: [
      F('premise', '故事前提', { multiline: true }),
      F('central_conflict', '核心冲突', { multiline: true }),
      F('protagonist_goal', '主角目标'),
      F('stakes', '代价'),
      F('dramatic_question', '戏剧问题'),
      F('story_promise', '故事承诺'),
      F('genre', '题材'),
      F('tone', '基调'),
      F('constraints', '约束', { list: true }),
    ],
  },
  theme: {
    label: '主题', icon: 'story',
    cardFields: ['theme', 'statement'],
    fields: [F('theme', '主题'), F('statement', '主题陈述', { multiline: true }),
      F('counter_theme', '反向主题'), F('motifs', '意象', { list: true })],
  },
  world: {
    label: '世界', icon: 'world',
    cardFields: ['rules', 'factions', 'locations'],
    fields: [
      F('rules', '世界规则', { list: true }),
      F('locations', '地点', { list: true }),
      F('factions', '势力', { list: true }),
      F('resources', '资源', { list: true }),
      F('technology_or_magic', '技术 / 魔法', { multiline: true }),
      F('history', '与故事相关的历史', { list: true }),
    ],
  },
  character: {
    label: '人物', icon: 'character',
    cardFields: ['name', 'role', 'goal', 'conflict'],
    fields: [
      F('name', '名字'), F('role', '身份 / 角色功能'),
      F('goal', '目标', { multiline: true }),
      F('motivation', '动机', { multiline: true }),
      F('conflict', '冲突', { multiline: true }),
      F('flaw', '缺陷'), F('fear', '恐惧'),
      F('strengths', '长处', { list: true }),
      F('relationships', '关系', { list: true }),
    ],
  },
  character_arc: {
    label: '人物弧', icon: 'relationship',
    cardFields: ['character_id', 'crisis', 'end_state'],
    fields: [
      F('character_id', '对应人物'),
      F('start_state', '起点'),
      F('internal_conflict', '内在冲突', { multiline: true }),
      F('external_pressure', '外部压力', { multiline: true }),
      F('turns', '转折', { list: true }),
      F('crisis', '危机', { multiline: true }),
      F('climax_choice', '关键选择', { multiline: true }),
      F('end_state', '终点'),
    ],
  },
  story_arc: {
    label: '故事弧', icon: 'story',
    cardFields: ['initial_state', 'crisis', 'resolution'],
    fields: [
      F('initial_state', '初始状态', { multiline: true }),
      F('inciting_incident', '触发事件', { multiline: true }),
      F('midpoint', '中点', { multiline: true }),
      F('major_turns', '主要转折', { list: true }),
      F('crisis', '危机', { multiline: true }),
      F('climax', '高潮', { multiline: true }),
      F('resolution', '结局', { multiline: true }),
    ],
  },
  structural_unit: {
    label: '结构单元', icon: 'outline',
    cardFields: ['title', 'goal', 'turn', 'outcome'],
    fields: [
      F('unit_type', '单元类型（幕 / 卷 / 弧）'),
      F('title', '标题'), F('goal', '目标', { multiline: true }),
      F('conflict', '冲突', { multiline: true }),
      F('turn', '转折', { multiline: true }),
      F('outcome', '结果', { multiline: true }),
      F('child_units', '下级单元', { list: true }),
    ],
  },
  chapter: {
    label: '章节', icon: 'chapter',
    cardFields: ['title', 'goal', 'conflict', 'turn', 'outcome', 'hook'],
    fields: [
      F('title', '标题'), F('goal', '章节目标', { multiline: true }),
      F('pov', '叙事视角'), F('characters', '出场角色', { list: true }),
      F('location', '地点'),
      F('conflict', '冲突', { multiline: true }),
      F('turn', '转折', { multiline: true }),
      F('outcome', '结果', { multiline: true }),
      F('hook', '结尾钩子', { multiline: true }),
      F('setup', '埋下的伏笔', { list: true }),
      F('payoff', '回收的伏笔', { list: true }),
    ],
  },
  scene: {
    label: '场景', icon: 'simulation',
    cardFields: ['scene_purpose', 'conflict', 'turn', 'outcome', 'next_hook'],
    fields: [
      F('chapter_id', '所属章节'),
      F('pov', '视角'),
      F('location', '地点'), F('time', '时间'),
      F('scene_purpose', '场景目的', { multiline: true }),
      F('character_goals', '角色目标', { list: true }),
      F('conflict', '冲突', { multiline: true }),
      F('escalation', '升级', { multiline: true }),
      F('turn', '转折', { multiline: true }),
      F('outcome', '结果', { multiline: true }),
      F('information_reveal', '揭示的信息', { list: true }),
      F('character_change', '人物变化', { multiline: true }),
      F('relationship_change', '关系变化', { multiline: true }),
      F('setup', '埋下的伏笔', { list: true }),
      F('payoff', '回收的伏笔', { list: true }),
      F('next_hook', '下一个钩子', { multiline: true }),
      F('story_function', '故事功能（这场戏为什么存在）', { list: true }),
    ],
  },
  setup: {
    label: '伏笔', icon: 'foreshadow',
    cardFields: ['content', 'expected_payoff', 'status'],
    fields: [F('content', '伏笔内容', { multiline: true }),
      F('expected_payoff', '预期回收方式', { multiline: true }),
      F('status', '回收状态')],
  },
  payoff: {
    label: '回收', icon: 'complete',
    cardFields: ['result', 'status'],
    fields: [F('resolves_setup_ids', '回收的伏笔', { list: true }),
      F('result', '回收结果', { multiline: true }), F('status', '状态')],
  },
  causal_link: {
    label: '因果连接', icon: 'relationship',
    cardFields: ['source_node', 'relation', 'target_node'],
    fields: [F('source_node', '起点'), F('relation', '关系'),
      F('target_node', '终点'), F('reason', '原因', { multiline: true })],
  },
}

export const FALLBACK_NODE_SPEC: NodeTypeSpec = {
  label: '内容', icon: 'book', cardFields: [], fields: [],
}

export function nodeTypeSpec(nodeType: string): NodeTypeSpec {
  return NODE_TYPE_SPECS[String(nodeType || '')] ?? FALLBACK_NODE_SPEC
}

export function nodeTypeLabel(nodeType: string): string {
  return nodeTypeSpec(nodeType).label
}

export function nodeTypeIcon(nodeType: string): string {
  return nodeTypeSpec(nodeType).icon
}

export function fieldLabel(nodeType: string, field: string): string {
  const spec = nodeTypeSpec(nodeType)
  const found = spec.fields.find((row) => row.key === field)
  return found?.label ?? field
}

export function fieldSpec(nodeType: string, field: string): FieldSpec {
  const spec = nodeTypeSpec(nodeType)
  return spec.fields.find((row) => row.key === field) ?? { key: field, label: field }
}

export function isMultilineField(nodeType: string, field: string): boolean {
  return Boolean(fieldSpec(nodeType, field).multiline)
}

/** 场景故事功能 → 作者语言（§25：不藏进高级字段）。 */
export const STORY_FUNCTION_LABELS: Record<string, string> = {
  advance_plot: '推进主线',
  reveal_information: '揭示信息',
  escalate_conflict: '升级冲突',
  character_change: '人物变化',
  relationship_change: '关系变化',
  setup: '埋下伏笔',
  payoff: '回收伏笔',
  decision: '做出决定',
  reversal: '转折',
  transition: '过渡',
}

export function storyFunctionLabel(value: string): string {
  return STORY_FUNCTION_LABELS[String(value || '')] ?? String(value || '')
}

/** 因果关系 → 作者语言（§44：A 导致/支持/阻止 B）。 */
export const CAUSAL_RELATION_LABELS: Record<string, string> = {
  causes: '导致',
  enables: '使可能',
  blocks: '阻止',
  reveals: '揭示',
  motivates: '驱动',
  pays_off: '回收',
}

export function causalRelationLabel(value: string): string {
  return CAUSAL_RELATION_LABELS[String(value || '')] ?? String(value || '')
}

/** 结构单元类型 → 作者语言（不写死「第一幕」；§22）。 */
export const UNIT_TYPE_LABELS: Record<string, string> = {
  act: '幕', volume: '卷', arc: '弧',
}

export function unitTypeLabel(value: string): string {
  return UNIT_TYPE_LABELS[String(value || '')] ?? (value || '单元')
}

/** 值 → 单行可读文本（列表用「、」连接；不输出原始 JSON）。 */
export function displayValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) {
    return value.map((row) => displayValue(row)).filter(Boolean).join('、')
  }
  if (typeof value === 'object') {
    const row = value as Record<string, unknown>
    const parts = Object.entries(row).map(([key, item]) => `${key}: ${displayValue(item)}`)
    return parts.join('，')
  }
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

export function nodeTitle(node: { node_type: string; visible?: Record<string, unknown>
  payload?: Record<string, unknown> }): string {
  const data = { ...(node.payload ?? {}), ...(node.visible ?? {}) }
  const primary = ['title', 'name', 'premise', 'content', 'purpose', 'theme', 'result']
  for (const key of primary) {
    const value = displayValue(data[key])
    if (value) return value.length > 48 ? `${value.slice(0, 48)}…` : value
  }
  return nodeTypeLabel(node.node_type)
}
