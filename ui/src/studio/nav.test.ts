/*
 * 导航模型测试（Closure Gate §9）：一级导航边界、路由解析、刷新安全表示。
 */
import { describe, expect, it } from 'vitest'
import { PRIMARY_LABELS, STUDIO_NAV, parseStudioRoute, studioHash } from './nav'

describe('studio navigation', () => {
  it('has the frozen 6 primary + 3 auxiliary entries', () => {
    const primary = STUDIO_NAV.filter((row) => row.group === 'primary')
      .map((row) => row.label)
    const aux = STUDIO_NAV.filter((row) => row.group === 'aux').map((row) => row.label)
    expect(primary).toEqual(['总览', '创造', '世界', '人物', '故事', '场景', '检查'])
    expect(aux).toEqual(['Agent', '交付', '插件'])
    expect(PRIMARY_LABELS).toEqual(primary)
    expect(STUDIO_NAV.length).toBeLessThanOrEqual(10)
  })

  it('parses deep links into a refresh-safe route', () => {
    expect(parseStudioRoute('#/studio')).toMatchObject({ name: 'landing' })
    expect(parseStudioRoute('#/studio/n/alpha')).toMatchObject(
      { name: 'studio', novelId: 'alpha', view: 'overview', entityId: '' })
    expect(parseStudioRoute('#/studio/n/alpha/scenes/sc_001_01')).toMatchObject(
      { novelId: 'alpha', view: 'scenes', entityId: 'sc_001_01' })
    expect(parseStudioRoute('#/studio/n/alpha/quality/QI_X')).toMatchObject(
      { view: 'quality', entityId: 'QI_X' })
    expect(parseStudioRoute('#/studio/n/alpha/not-a-view')).toMatchObject(
      { view: 'overview' })
    // post-release cleanup：旧入口不再有独立路由，由 App.tsx 归一化到 Studio；
    // 解析器把它们当作 landing（第一方产品面），绝不解析出第二套产品路由。
    expect(parseStudioRoute('#/story-builder?novel_id=alpha'))
      .toMatchObject({ name: 'landing' })
    expect(parseStudioRoute('#/v3/n/alpha')).toMatchObject({ name: 'landing' })
  })

  it('round-trips hash representations (back/forward safe)', () => {
    const hash = studioHash('alpha', 'scenes', 'sc_001_01')
    expect(hash).toBe('#/studio/n/alpha/scenes/sc_001_01')
    expect(studioHash('alpha')).toBe('#/studio/n/alpha')
    expect(studioHash('', 'overview')).toBe('#/studio')
    expect(parseStudioRoute(hash).entityId).toBe('sc_001_01')
  })
})
