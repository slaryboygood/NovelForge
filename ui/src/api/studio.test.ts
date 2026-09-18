/*
 * Studio HTTP 客户端 wire-contract 测试（Closure Gate §14、§15）。
 *
 * 只验证「UI 发的请求形状」与「错误映射」；不重复后端业务测试。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api'
import { deliveryArtifactUrl, studioApi } from './studio'

interface Call {
  url: string
  init: RequestInit
  body: Record<string, unknown>
}

let calls: Call[] = []
let responses: { status?: number; payload: unknown }[] = []

function mockFetch() {
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit = {}) => {
    const body = init.body ? JSON.parse(String(init.body)) : {}
    calls.push({ url: String(url), init, body })
    const next = responses.shift() ?? { payload: {} }
    const status = next.status ?? 200
    return {
      ok: status >= 200 && status < 300,
      status,
      statusText: 'mock',
      json: async () => next.payload,
      text: async () => JSON.stringify(next.payload),
    } as unknown as Response
  }))
}

beforeEach(() => {
  responses = []
  mockFetch()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('studioApi read endpoints', () => {
  it('requests overview / blueprint / quality / formats / plugins with explicit novel scope', async () => {
    responses = [{ payload: {} }, { payload: {} }, { payload: {} },
      { payload: {} }, { payload: {} }]
    await studioApi.overview('alpha', 'accepted')
    await studioApi.blueprint('alpha', 'scene', 'current')
    await studioApi.quality('alpha', 'Q8', 'open')
    await studioApi.deliveryFormats('alpha')
    await studioApi.plugins()
    expect(calls[0].url).toBe('/api/story-builder/studio/overview?novel_id=alpha&mode=accepted')
    expect(calls[1].url).toContain('node_type=scene')
    expect(calls[2].url).toContain('gate=Q8')
    expect(calls[3].url).toBe('/api/story-builder/studio/delivery/formats?novel_id=alpha')
    expect(calls[4].url).toBe('/api/story-builder/studio/plugins')
  })

  it('builds artifact download URLs on the delivery contract', () => {
    expect(deliveryArtifactUrl('alpha', 'DS_1', 'exports/blueprint.md'))
      .toBe('/api/story-builder/delivery/DS_1/artifacts/exports/blueprint.md?novel_id=alpha')
  })
})

describe('studioApi write endpoints', () => {
  it('patch sends field-level changes with expected_revision', async () => {
    responses = [{ payload: { revision: 3 } }]
    await studioApi.patch('alpha', 'sc_001_01', {
      changes: { outcome: '新结果' }, expected_revision: 2, reason: '作者手动修改' })
    expect(calls[0].url).toBe('/api/story-builder/editor/nodes/sc_001_01')
    expect(calls[0].init.method).toBe('PATCH')
    expect(calls[0].body).toMatchObject({ novel_id: 'alpha',
      changes: { outcome: '新结果' }, expected_revision: 2 })
  })

  it('rewrite preserves dry_run semantics and target fields', async () => {
    responses = [{ payload: {} }, { payload: {} }]
    await studioApi.rewrite('alpha', 'ch_001', { target_fields: ['hook'],
      instruction: '更有悬念', expected_revision: 4, dry_run: true })
    await studioApi.rewrite('alpha', 'ch_001', { target_fields: ['hook'],
      instruction: '更有悬念', expected_revision: 4, dry_run: false })
    const preview = calls[0].body as Record<string, unknown>
    expect(calls[0].url).toBe('/api/story-builder/editor/nodes/ch_001/rewrite')
    expect(calls[0].body).toMatchObject({ target_fields: ['hook'], dry_run: true })
    expect((calls[1].body as Record<string, unknown>).dry_run).toBe(false)
    expect(calls[0].body).toMatchObject({ expected_revision: 4 })
    expect(preview.target_fields).toEqual(['hook'])
  })

  it('accept / reject / restore follow the frozen editor contract', async () => {
    responses = [{ payload: {} }, { payload: {} }, { payload: {} }]
    await studioApi.accept('alpha', 'ch_001', { revision: 2 })
    await studioApi.reject('alpha', 'ch_001', { revision: 2 })
    await studioApi.restore('alpha', 'ch_001', { from_revision: 1 })
    expect(calls[0].url).toBe('/api/story-builder/editor/nodes/ch_001/accept')
    expect(calls[1].url).toBe('/api/story-builder/editor/nodes/ch_001/reject')
    expect(calls[2].url).toBe('/api/story-builder/editor/nodes/ch_001/restore')
    expect(calls[2].body).toMatchObject({ novel_id: 'alpha', from_revision: 1 })
  })

  it('quality evaluate / repair(preview+execute) / verify keep dry_run explicit', async () => {
    responses = [{ payload: {} }, { payload: {} }, { payload: {} }, { payload: {} }]
    await studioApi.evaluateQuality({ novel_id: 'alpha' })
    await studioApi.planRepair({ novel_id: 'alpha', issue_ids: ['QI_1'] })
    await studioApi.executeRepair({ novel_id: 'alpha', issue_ids: ['QI_1'] })
    await studioApi.verifyRepair({ novel_id: 'alpha', issue_ids: ['QI_1'] })
    expect(calls[0].url).toBe('/api/story-builder/studio/quality/evaluate')
    expect(calls[1].body).toMatchObject({ dry_run: true, issue_ids: ['QI_1'] })
    expect(calls[2].body).toMatchObject({ dry_run: false, issue_ids: ['QI_1'] })
    expect(calls[3].url).toBe('/api/story-builder/studio/quality/verify')
  })

  it('deliver sends selection semantics on the delivery endpoint', async () => {
    responses = [{ payload: { status: 'delivered' } }]
    await studioApi.deliver({ novel_id: 'alpha', formats: ['markdown'],
      selection_mode: 'accepted', require_accepted: true,
      require_quality_pass: true })
    expect(calls[0].url).toBe('/api/story-builder/delivery')
    expect(calls[0].body).toMatchObject({ selection_mode: 'accepted',
      formats: ['markdown'], require_accepted: true, require_quality_pass: true })
  })
})

describe('studioApi generation contract (Closure Gate §15)', () => {
  it('sends explicit parent_id and sibling index (two chapters → distinct nodes)', async () => {
    responses = [{ payload: { node: { node_id: 'ch_001' } } },
      { payload: { node: { node_id: 'ch_002' } } }]
    await studioApi.generate({ novel_id: 'alpha', task: 'chapter',
      parent_id: 'act_01', index: 1 })
    await studioApi.generate({ novel_id: 'alpha', task: 'chapter',
      parent_id: 'act_01', index: 2 })
    expect(calls[0].body).toMatchObject({ task: 'chapter', parent_id: 'act_01', index: 1 })
    expect(calls[1].body).toMatchObject({ task: 'chapter', parent_id: 'act_01', index: 2 })
    expect(calls[0].body.index).not.toBe(calls[1].body.index)
  })

  it('omits parent_id for root tasks and keeps sequence when provided', async () => {
    responses = [{ payload: {} }, { payload: {} }]
    await studioApi.generate({ novel_id: 'alpha', task: 'premise' })
    await studioApi.generate({ novel_id: 'alpha', task: 'scene', parent_id: 'ch_001',
      sequence: 2 })
    expect(calls[0].body).not.toHaveProperty('parent_id')
    expect(calls[1].body).toMatchObject({ parent_id: 'ch_001', sequence: 2 })
  })
})

describe('studioApi error surface', () => {
  it('propagates stable error codes through ApiError for UI mapping', async () => {
    responses = [{ status: 409, payload: { detail: { code: 'EDITOR_REVISION_CONFLICT',
      message: '内容已经被更新' } } }]
    await expect(studioApi.patch('alpha', 'ch_001', { changes: {},
      expected_revision: 1 })).rejects.toBeInstanceOf(ApiError)
    responses = [{ status: 422, payload: { detail: { code: 'GENERATION_UNAVAILABLE',
      message: '未配置模型' } } }]
    const failure = await studioApi.generate({ novel_id: 'alpha', task: 'premise' })
      .catch((reason) => reason)
    expect(failure.detail.code).toBe('GENERATION_UNAVAILABLE')
    expect(String(failure.message)).not.toMatch(/traceback/i)
  })
})
