/*
 * NovelForge V3 NavigationModel（唯一路由与深链接来源）。
 *
 * 路由形状：
 *   #/                             → Novel Landing（存档选择）
 *   #/n/<novelId>                  → Novel Command Center
 *   #/n/<novelId>/<view>?step=&group=&panel=  → 某个创作工作区
 *   #/story-builder?...            → V2 legacy（高级工具 / 兼容入口）
 *
 * 一级导航只有 主页 + 8 个作者工作区；Inspector / Repair 等高级工具不进入一级导航，
 * 通过工作区内的“高级工具”入口打开 legacy 面板（同一套 domain 规则）。
 */

export type V3View = 'home' | 'creation' | 'world' | 'characters' | 'story'
  | 'simulation' | 'outline' | 'review' | 'export'

export interface NavItem {
  view: V3View
  label: string
  icon: string
  stageId: string
}

export const PRIMARY_NAV: NavItem[] = [
  { view: 'home', label: '首页', icon: 'home', stageId: '' },
  { view: 'creation', label: '创作', icon: 'creation', stageId: 'creation' },
  { view: 'world', label: '世界', icon: 'world', stageId: 'world' },
  { view: 'characters', label: '角色', icon: 'character', stageId: 'characters' },
  { view: 'story', label: '故事', icon: 'story', stageId: 'story' },
  { view: 'simulation', label: '推演', icon: 'simulation', stageId: 'simulation' },
  { view: 'outline', label: '大纲', icon: 'outline', stageId: 'outline' },
  { view: 'review', label: '检查', icon: 'review', stageId: 'review' },
  { view: 'export', label: '导出', icon: 'export', stageId: 'export' },
]

const VIEW_IDS = new Set<string>(PRIMARY_NAV.map((row) => row.view))

export function isV3View(value: string): value is V3View {
  return VIEW_IDS.has(value)
}

export interface DeepLinkParams {
  step?: string
  group?: string
  panel?: string
}

export type Route =
  | { name: 'landing' }
  | { name: 'novel'; novelId: string; view: V3View; params: DeepLinkParams }
  | { name: 'legacy'; query: string }

/** V2 legacy 面板入口（高级工具），始终带上 novel_id 上下文。 */
export function legacyHash(novelId: string, tab: string, extra: DeepLinkParams = {}): string {
  const params = new URLSearchParams()
  if (novelId) params.set('novel_id', novelId)
  if (tab) params.set('tab', tab)
  for (const key of ['step', 'group'] as const) {
    const value = extra[key]
    if (value) params.set(key, value)
  }
  const query = params.toString()
  return '#/story-builder' + (query ? `?${query}` : '')
}

export function novelHash(novelId: string, view: V3View = 'home',
  params: DeepLinkParams = {}): string {
  const search = new URLSearchParams()
  for (const key of ['step', 'group', 'panel'] as const) {
    const value = params[key]
    if (value) search.set(key, value)
  }
  const query = search.toString()
  const base = view === 'home' ? `#/n/${encodeURIComponent(novelId)}`
    : `#/n/${encodeURIComponent(novelId)}/${view}`
  return query ? `${base}?${query}` : base
}

export function parseRoute(hash: string): Route {
  const raw = (hash || '').replace(/^#/, '')
  if (!raw || raw === '/') return { name: 'landing' }
  if (raw.startsWith('/story-builder')) {
    const query = raw.includes('?') ? raw.slice(raw.indexOf('?') + 1) : ''
    return { name: 'legacy', query }
  }
  if (raw.startsWith('/n/')) {
    const [path, query = ''] = raw.split('?')
    const segments = path.split('/').filter(Boolean) // ['n', novelId, view?]
    const novelId = decodeURIComponent(segments[1] ?? '')
    const viewRaw = segments[2] ?? 'home'
    const view = isV3View(viewRaw) ? viewRaw : 'home'
    const params: DeepLinkParams = {}
    const search = new URLSearchParams(query)
    for (const key of ['step', 'group', 'panel'] as const) {
      const value = search.get(key)
      if (value) params[key] = value
    }
    if (!novelId) return { name: 'landing' }
    return { name: 'novel', novelId, view, params }
  }
  return { name: 'landing' }
}

export function routeHash(route: Route): string {
  if (route.name === 'landing') return '#/'
  if (route.name === 'legacy') return `#/story-builder${route.query ? `?${route.query}` : ''}`
  return novelHash(route.novelId, route.view, route.params)
}

/** 工作区标题（作者语言，不出现内部模块名）。 */
export const VIEW_TITLES: Record<V3View, string> = {
  home: '总览',
  creation: '创作',
  world: '世界',
  characters: '角色',
  story: '故事',
  simulation: '推演',
  outline: '大纲',
  review: '检查',
  export: '导出',
}
