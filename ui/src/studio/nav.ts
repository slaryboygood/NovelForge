/*
 * Story Studio 导航与深链接（`docs/v4/V4_UI_CONTRACT.md` §3）。
 *
 * 路由形状：
 *   #/studio                              作品选择 / 新建
 *   #/studio/n/<novelId>                  Overview
 *   #/studio/n/<novelId>/<view>[/<id>]    某个工作区（可深链接实体）
 *
 * 旧入口（`#/v3/...`、`#/story-builder?...`）在 post-release cleanup 后
 * 由 `ui/src/App.tsx` 归一化到 Story Studio；本模块不再有第二套产品路由。
 */

export type StudioView = 'overview' | 'creation' | 'world' | 'characters' | 'story'
  | 'scenes' | 'quality' | 'agent' | 'delivery' | 'plugins' | 'settings'

export interface StudioNavItem {
  view: StudioView
  label: string
  icon: string
  hint: string
  group: 'primary' | 'aux'
}

export const STUDIO_NAV: StudioNavItem[] = [
  { view: 'overview', label: '总览', icon: 'home', group: 'primary',
    hint: '这本作品现在做到哪里' },
  { view: 'creation', label: '创造', icon: 'creation', group: 'primary',
    hint: '前提 / 主题 / 核心冲突' },
  { view: 'world', label: '世界', icon: 'world', group: 'primary',
    hint: '规则 / 地点 / 势力 / 资源' },
  { view: 'characters', label: '人物', icon: 'character', group: 'primary',
    hint: '人物卡与人物弧' },
  { view: 'story', label: '故事', icon: 'story', group: 'primary',
    hint: '故事弧 / 结构单元 / 章节' },
  { view: 'scenes', label: '场景', icon: 'simulation', group: 'primary',
    hint: '每场戏为什么存在' },
  { view: 'quality', label: '检查', icon: 'review', group: 'primary',
    hint: '质量问题与定向修复' },
  { view: 'agent', label: 'Agent', icon: 'objective', group: 'aux',
    hint: '给出目标，先看计划再执行' },
  { view: 'delivery', label: '交付', icon: 'export', group: 'aux',
    hint: '选择 / 预检 / 下载' },
  { view: 'plugins', label: '插件', icon: 'locked', group: 'aux',
    hint: '扩展能力的只读状态' },
]

const VIEWS = new Set<string>(STUDIO_NAV.map((row) => row.view))

export function isStudioView(value: string): value is StudioView {
  return VIEWS.has(value)
}

/** 一级 / 辅助导航文案（测试与门禁冻结此边界，§9）。 */
export const PRIMARY_LABELS: string[] = STUDIO_NAV
  .filter((row) => row.group === 'primary').map((row) => row.label)

export interface StudioRoute {
  name: 'landing' | 'studio'
  novelId: string
  view: StudioView
  entityId: string
  query: string
}

export function studioHash(novelId: string, view: StudioView = 'overview',
  entityId = ''): string {
  if (!novelId) return '#/studio'
  const base = `#/studio/n/${encodeURIComponent(novelId)}`
  const parts = [base]
  if (view && view !== 'overview') parts.push(view)
  if (entityId) parts.push(encodeURIComponent(entityId))
  return parts.join('/')
}

export function parseStudioRoute(hash: string): StudioRoute {
  const raw = String(hash || '').replace(/^#/, '')
  const [path, query = ''] = raw.split('?')
  if (!path || path === '/' || path === '/studio') {
    return { name: 'landing', novelId: '', view: 'overview', entityId: '', query }
  }
  const segments = path.split('/').filter(Boolean)     // ['studio','n',novel,view?,id?]
  if (segments[0] !== 'studio' || segments[1] !== 'n') {
    return { name: 'landing', novelId: '', view: 'overview', entityId: '', query }
  }
  const novelId = decodeURIComponent(segments[2] ?? '')
  const viewRaw = segments[3] ?? 'overview'
  const view = isStudioView(viewRaw) ? viewRaw : 'overview'
  const entityId = segments[4] ? decodeURIComponent(segments[4]) : ''
  if (!novelId) {
    return { name: 'landing', novelId: '', view, entityId: '', query }
  }
  return { name: 'studio', novelId, view, entityId, query }
}

/** 工作区内可深链接的实体类型（刷新不丢位置，§60）。 */
export const ENTITY_VIEWS: Partial<Record<StudioView, string>> = {
  characters: 'character', story: 'chapter', scenes: 'scene', quality: 'issue',
  delivery: 'snapshot',
}
