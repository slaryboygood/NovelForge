/*
 * 父节点解析单元测试（Closure Gate §3、§4、§15）。
 *
 * 冻结规则：explicit > fresh reload 结果；0 → missing；1 → 自动；≥2 → 要求选择；
 * pre-selection 只在仍然合法时生效（绝不 latest-wins / highest sequence / last item）。
 */
import { describe, expect, it } from 'vitest'
import { parentOptions, resolveParent } from './parents'
import type { StudioNode } from '../../api/studio'

function node(nodeId: string, nodeType: string, payload: Record<string, unknown> = {},
  sequence = 0): StudioNode {
  return { node_id: nodeId, node_type: nodeType, revision: 1, status: 'proposed',
    sequence, payload, visible: payload }
}

const CHAPTERS = [node('ch_001', 'chapter', { title: '第一章' }, 1),
  node('ch_002', 'chapter', { title: '第二章' }, 2)]

describe('resolveParent', () => {
  it('uses the explicit parent when the caller provides one', () => {
    const result = resolveParent('scene', 'ch_999', CHAPTERS)
    expect(result.status).toBe('explicit')
    expect(result.parentId).toBe('ch_999')
  })

  it('reports missing when there is no legal parent', () => {
    const result = resolveParent('scene', '', [node('world', 'world')])
    expect(result.status).toBe('missing')
    expect(result.parentId).toBe('')
    expect(result.message).toContain('chapter')
  })

  it('auto-selects when exactly one legal parent exists', () => {
    const result = resolveParent('scene', '', [CHAPTERS[0]])
    expect(result.status).toBe('resolved')
    expect(result.parentId).toBe('ch_001')
  })

  it('requires an explicit choice when multiple legal parents exist', () => {
    const result = resolveParent('scene', '', CHAPTERS)
    expect(result.status).toBe('ambiguous')
    expect(result.options.map((row) => row.nodeId)).toEqual(['ch_001', 'ch_002'])
    expect(result.message).toContain('选择')
  })

  it('pre-selects the generated node when it is still a legal parent', () => {
    const result = resolveParent('scene', '', CHAPTERS, 'ch_002')
    expect(result.status).toBe('ambiguous')
    expect(result.parentId).toBe('ch_002')      // 预选（仍需作者确认）
  })

  it('does not silently use a pre-selection that is no longer legal', () => {
    const result = resolveParent('scene', '', CHAPTERS, 'ch_deleted')
    expect(result.status).toBe('ambiguous')
    expect(result.parentId).toBe('')            // 不静默退回 latest / last item
  })

  it('root tasks need no parent', () => {
    const result = resolveParent('premise', '', CHAPTERS)
    expect(result.status).toBe('root')
    expect(result.parentId).toBe('')
  })

  it('follows the real backend parent rules', () => {
    // scene → chapter
    expect(parentOptions('scene', CHAPTERS).map((row) => row.nodeId))
      .toEqual(['ch_001', 'ch_002'])
    // chapter → structural_unit | story_arc（顺序按 task 契约）
    const units = [node('story_arc', 'story_arc'), node('act_01', 'structural_unit')]
    expect(parentOptions('chapter', units).map((row) => row.nodeId))
      .toEqual(['act_01', 'story_arc'])
    // character_arc → character
    expect(parentOptions('character_arc', [node('char_01', 'character')])
      .map((row) => row.nodeId)).toEqual(['char_01'])
    // structural_unit → story_arc
    expect(parentOptions('structural_unit', units).map((row) => row.nodeId))
      .toEqual(['story_arc'])
  })

  it('never picks a parent by sequence or array order when ambiguous', () => {
    const reversed = [CHAPTERS[1], CHAPTERS[0]]
    const result = resolveParent('scene', '', reversed)
    expect(result.status).toBe('ambiguous')
    expect(result.parentId).toBe('')            // 不以 sequence / 顺序取“最新”
    expect(result.options.map((row) => row.nodeId)).toEqual(['ch_001', 'ch_002'])
  })
})
