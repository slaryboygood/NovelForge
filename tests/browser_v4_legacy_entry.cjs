/*
 * NovelForge V4-10 Closure Gate §19：兼容入口 smoke gate（当前环境可执行）。
 *
 * 验证三件事（不改动任何历史验收断言）：
 *   · 默认 URL            → Story Studio（V4 主产品面）
 *   · ?ui=v3 / #/v3...    → V3 工作台（显式兼容入口）
 *   · ?ui=v2 / #/story-builder → V2 / Story Builder（显式兼容入口）
 *   · 无页面错误、无重定向循环、兼容模式必须是显式的
 *
 * 历史 V3/V2 完整验收（tests/browser_v3_*.cjs 等）需要作者 acceptance data root；
 * 本环境不存在这些数据 → 完整验收 NOT RUN（见最终报告 §20/§26）。
 *
 * 运行：
 *   .venv\\Scripts\\python.exe scripts/studio_ui_test_server.py --port 8040 --root workspace/studio_ui_test_root
 *   node tests/browser_v4_legacy_entry.cjs
 */
const { chromium } = require('playwright')
const assert = require('node:assert/strict')

const BASE = process.env.STUDIO_BASE || 'http://127.0.0.1:8040'
const errors = []

async function open(page, url) {
  errors.length = 0
  page.removeAllListeners('pageerror')
  page.on('pageerror', (error) => errors.push(error.message))
  const navigations = []
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame()) navigations.push(frame.url())
  })
  await page.goto(url, { waitUntil: 'networkidle' })
  await page.waitForTimeout(400)
  return navigations
}

;(async () => {
  const browser = await chromium.launch({ channel: 'msedge' })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })

  // 1) 默认入口 = Story Studio
  await open(page, `${BASE}/#/studio`)
  await page.waitForSelector('[data-testid="studio-landing"]', { timeout: 15000 })
  assert.deepEqual(errors, [], `默认入口出现页面错误：${errors.join('; ')}`)

  // 2) V3 显式兼容入口
  const v3Nav = await open(page, `${BASE}/?ui=v3`)
  await page.waitForSelector('.v3-root', { timeout: 15000 })
  // V3 首屏是 Novel Landing（没有作品数据时），进入作品后才是 AppShell；
  // 这里只验证「V3 产品面渲染」而不断言具体数据。
  await page.waitForSelector('[data-testid="v3-landing"], [data-testid="v3-app-shell"]',
    { timeout: 15000 })
  assert.deepEqual(errors, [], `V3 入口出现页面错误：${errors.join('; ')}`)
  assert.ok(v3Nav.every((url) => url.includes('ui=v3')),
    `V3 入口发生非预期跳转：${v3Nav.join(' -> ')}`)
  assert.ok(!(await page.locator('[data-testid="studio-shell"]').count()),
    'V3 入口错误地渲染了 Story Studio')

  // 2b) #/v3 深链接同样进入 V3
  await open(page, `${BASE}/?ui=v3#/v3`)
  await page.waitForSelector('.v3-root', { timeout: 15000 })
  assert.ok(!(await page.locator('[data-testid="studio-landing"]').count()),
    '#/v3 深链接错误地渲染了 Story Studio')

  // 3) V2 显式兼容入口
  const v2Nav = await open(page, `${BASE}/?ui=v2`)
  await page.waitForSelector('.story-builder-page, .story-builder-empty',
    { timeout: 15000 })
  assert.deepEqual(errors, [], `V2 入口出现页面错误：${errors.join('; ')}`)
  assert.ok(v2Nav.every((url) => url.includes('ui=v2')),
    `V2 入口发生非预期跳转：${v2Nav.join(' -> ')}`)
  assert.ok(!(await page.locator('[data-testid="studio-shell"]').count()),
    'V2 入口错误地渲染了 Story Studio')

  // 3b) #/story-builder 深链接进入 V2（显式入口之外的 hash 兼容）
  await open(page, `${BASE}/?ui=v2#/story-builder`)
  await page.waitForSelector('.story-builder-page, .story-builder-empty',
    { timeout: 15000 })

  // 4) 兼容模式必须是显式的：默认 URL 绝不渲染 V3 / V2 外壳
  await open(page, `${BASE}/`)
  await page.waitForSelector('[data-testid="studio-landing"]', { timeout: 15000 })
  assert.ok(!(await page.locator('.v3-root').count()),
    '默认 URL 渲染了 V3 外壳（兼容入口没有显式化）')
  assert.ok(!(await page.locator('.story-builder-page').count()),
    '默认 URL 渲染了 V2 外壳（兼容入口没有显式化）')
  assert.deepEqual(errors, [], `默认 URL 出现页面错误：${errors.join('; ')}`)

  await browser.close()
  console.log('V4-10 legacy entry compatibility gate: PASS')
})().catch((error) => {
  console.error('V4-10 legacy entry compatibility gate: FAIL')
  console.error(error)
  process.exit(1)
})
