/*
 * 前端测试环境（V4-10 Closure Gate §5）。
 *
 * 只做最小配置：jsdom 环境由 vitest 提供；这里补 happy-dom 风格的断言清理与
 * 浏览器 API 的最小 polyfill（Playwright 不在 unit test 中使用）。
 */
import '@testing-library/react'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
})

if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}
