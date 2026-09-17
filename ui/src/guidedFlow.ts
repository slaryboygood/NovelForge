/**
 * W6-01 / W6-03 / W6-05：引导流状态、信息架构分组与深链接上下文。
 *
 * 这里只做 UI 侧的导航与展示映射：

 * - 阶段分组（设计 / 事实与推演 / 产出）与页签归属；
 * - 深链接上下文（novel_id / branch_id / package_id / step / group / tab）读写；
 * - 每个面板的“我在哪、下一步去哪”提示。
 */

export type CreatorTab =
  | 'guided' | 'builder' | 'world' | 'characters' | 'plot' | 'route' | 'outline'
  | 'progression' | 'memory' | 'director' | 'linkage'
  | 'overview' | 'mood' | 'regions' | 'relations' | 'compare' | 'tree'
  | 'inspector' | 'repair'

export type TabStage = 'design' | 'occurred' | 'output' | 'governance'

export const STAGE_ORDER: TabStage[] = ['design', 'occurred', 'output', 'governance']

export const STAGE_LABELS: Record<TabStage, string> = {
  design: '设计（故事构筑）',
  occurred: '事实与推演',
  output: '产出（路线 / 大纲）',
  governance: '检查与修复',
}

/** W6-03：页签分组（与 roadmap 的「设计 / 事实与推演 / 产出」一致）。 */
export const TAB_GROUPS: Array<{
  stage: TabStage
  tabs: Array<{ tab: CreatorTab; label: string; hint: string }>
}> = [
  {
    stage: 'design',
    tabs: [
      { tab: 'guided', label: '引导流', hint: '从一句创意开始，按步骤走到「开始推演」' },
      { tab: 'builder', label: '故事构筑', hint: '十步目录与设计树：逐节点确认设定' },
      { tab: 'overview', label: '设定总览', hint: '世界 / 主角 / 核心伙伴 / 势力 / 关系的卡片总览（只读）' },
      { tab: 'mood', label: '风格参考位', hint: '参考图 / 文字 mood（只存在本地，不写 StoryState）' },
    ],
  },
  {
    stage: 'occurred',
    tabs: [
      { tab: 'world', label: '世界面板', hint: '已发生事实：地点 / 资源 / 世界状态' },
      { tab: 'characters', label: '角色面板', hint: '已发生事实：角色与关系' },
      { tab: 'plot', label: '剧情面板', hint: '已发生事实：剧情线推进' },
      { tab: 'progression', label: '成长面板', hint: '已发生事实：成长与代价' },
      { tab: 'memory', label: '记忆面板', hint: '已发生事实：知识 / 伏笔 / 义务' },
      { tab: 'director', label: '导演面板', hint: '节奏与权重调整（不改事实）' },
      { tab: 'regions', label: '区域卡片', hint: '已知 / 未知区域、危险度、已知资源与进入条件' },
      { tab: 'relations', label: '关系网', hint: '人物—势力—伙伴关系与数值来源' },
    ],
  },
  {
    stage: 'output',
    tabs: [
      { tab: 'route', label: '路线实验室', hint: '试演 / 对比 / 合并 / 冻结分支' },
      { tab: 'outline', label: '大纲锻造', hint: '从冻结路线锻造四级大纲' },
      { tab: 'linkage', label: '大纲联动', hint: '版本对比与影响分析' },
      { tab: 'compare', label: '路线对比', hint: '两条分支差异并列高亮（列表形态）' },
      { tab: 'tree', label: '大纲结构树', hint: '全书 → 卷 → 篇章 → 章节，含节奏 / 钩子标记' },
    ],
  },
  {
    stage: 'governance',
    tabs: [
      { tab: 'inspector', label: 'Canon 检查器', hint: '跨层只读检索：Canon / StoryState / 历史 IR + 出处' },
      { tab: 'repair', label: '修复中心', hint: '诊断 → 预览 → 审批要求 → 执行既有 API → 结果追踪' },
    ],
  },
]

export function stageOfTab(tab: CreatorTab): TabStage {
  for (const group of TAB_GROUPS) {
    if (group.tabs.some((row) => row.tab === tab)) return group.stage
  }
  return 'design'
}

export function labelOfTab(tab: CreatorTab): string {
  for (const group of TAB_GROUPS) {
    const row = group.tabs.find((item) => item.tab === tab)
    if (row) return row.label
  }
  // NF-014：未知页签不能把内部 key 展示给作者（曾经显示「高级工具 · export」）。
  return '未知工具'
}

export function hintOfTab(tab: CreatorTab): string {
  for (const group of TAB_GROUPS) {
    const row = group.tabs.find((item) => item.tab === tab)
    if (row) return row.hint
  }
  return '这个页签在当前版本里不存在，已经回到默认面板。'
}

/** 未知页签是否为真实存在的页签（UI 用它决定是否回落到默认面板，而不是渲染空壳）。 */
export function isKnownTab(tab: CreatorTab | undefined): boolean {
  if (!tab) return false
  return TAB_GROUPS.some((group) => group.tabs.some((row) => row.tab === tab))
}

/** W6-05：深链接上下文（hash query，刷新后保持）。 */
export interface DeepLink {
  novel_id?: string
  tab?: CreatorTab
  step?: string
  group?: string
  branch_id?: string
  package_id?: string
  version?: string
}

export function readDeepLink(): DeepLink {
  try {
    const hash = window.location.hash || ''
    const query = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : ''
    const params = new URLSearchParams(query)
    const link: DeepLink = {}
    const novelId = params.get('novel_id') || ''
    const tab = params.get('tab') || ''
    if (novelId) link.novel_id = novelId
    if (tab) link.tab = tab as CreatorTab
    for (const key of ['step', 'group', 'branch_id', 'package_id', 'version'] as const) {
      const value = params.get(key)
      if (value) link[key] = value
    }
    return link
  } catch { return {} }
}

export function writeDeepLink(link: DeepLink) {
  try {
    const params = new URLSearchParams()
    for (const key of ['novel_id', 'tab', 'step', 'group', 'branch_id', 'package_id',
      'version'] as const) {
      const value = link[key]
      if (value) params.set(key, String(value))
    }
    const query = params.toString()
    const next = '#/story-builder' + (query ? '?' + query : '')
    if (window.location.hash !== next) window.location.hash = next
  } catch { /* 浏览器禁止时忽略深链接 */ }
}

export function withContext(link: DeepLink, context: DeepLink): DeepLink {
  return { ...context, ...link, novel_id: link.novel_id || context.novel_id }
}
