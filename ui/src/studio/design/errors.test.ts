/*
 * 错误映射测试（Closure Gate §8）：稳定 code → 作者语言，不泄漏内部细节。
 */
import { describe, expect, it } from 'vitest'
import { STUDIO_ERROR_MESSAGES, isConflict, mapError, sanitize } from './errors'

function apiError(code: string, message = 'boom', status = 400) {
  return { name: 'ApiError', message, status, detail: { code, message } }
}

describe('mapError', () => {
  it.each([
    ['EDITOR_REVISION_CONFLICT', '内容已经被更新'],
    ['DELIVERY_QUALITY_STALE', '还没有最新质量检查'],
    ['DELIVERY_QUALITY_FAILED', '质量检查未通过'],
    ['DELIVERY_NO_ACCEPTED_REVISION', '没有被接受'],
    ['DELIVERY_FORMAT_UNSUPPORTED', '格式不可用'],
    ['PLUGIN_PERMISSION_DENIED', '插件未获得该权限'],
    ['GENERATION_UNAVAILABLE', '未配置模型'],
  ])('maps %s to author language', (code, fragment) => {
    const info = mapError(apiError(code))
    expect(info.code).toBe(code)
    expect(info.message).toContain(fragment)
    expect(STUDIO_ERROR_MESSAGES[code]).toBeTruthy()
  })

  it('falls back for unknown codes without leaking internals', () => {
    const info = mapError(apiError('SOMETHING_NEW',
      'Traceback: File "C:\\Users\\alice\\a.py", line 3 ValueError'))
    expect(info.code).toBe('SOMETHING_NEW')
    expect(info.message).not.toMatch(/Traceback/)
    expect(info.message).not.toMatch(/C:\\Users/)
    expect(info.message).not.toMatch(/ValueError/)
    expect(info.message.length).toBeLessThanOrEqual(201)
  })

  it('sanitizes absolute paths and internal directories', () => {
    expect(sanitize('failed at C:\\Users\\alice\\novel\\x.json'))
      .not.toContain('C:\\Users')
    expect(sanitize('path /home/alice/novel/authoring/x')).not.toContain('/home/alice')
    expect(sanitize('novel/authoring/story_engine/plugins/x')).not.toContain('authoring')
  })

  it('detects revision conflicts for the conflict workflow', () => {
    expect(isConflict(apiError('EDITOR_REVISION_CONFLICT'))).toBe(true)
    expect(isConflict(apiError('DELIVERY_QUALITY_STALE'))).toBe(false)
  })

  it('never returns a raw ValidationError to the author', () => {
    const info = mapError({ name: 'ValidationError',
      message: '1 validation error for DeliveryBody\nnovel_id Field required' })
    expect(info.message).not.toMatch(/validation error/i)
  })
})
