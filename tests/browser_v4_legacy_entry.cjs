/*
 * NovelForge V4 legacy-entry gate（post-release cleanup 版本）。
 *
 * 背景：V4.0.0 之后的清理移除了 V2 / V3 两套产品 UI。旧入口不再加载旧 bundle，
 * 而是**回落（fallback）到 Story Studio**，保证旧书签不会 404 或空白。
 *
 * 验证四件事：
 *   · 默认 URL                     → Story Studio
 *   · `?ui=v3` / `#/v3...`         → Story Studio（不再渲染 V3 外壳）
 *   · `?ui=v2` / `#/story-builder` → Story Studio（不再渲染 V2 面板）
 *   · 0 page errors、0 redirect loop（只做一次 replaceState，不重新加载）
 *
 * 运行：
 *   .venv\Scripts\python.exe scripts/studio_ui_test_server.py --port 8040 --root workspace/studio_ui_test_root
 *   node tests/browser_v4_legacy_entry.cjs
 */
const { chromium } = require('playwright')
const assert = require('node:assert/strict')

const BASE = process.env.STUDIO_BASE || 'http://127.0.0.1:8040'
const errors = []

async function open(page, url) {
  errors.length = 0
  page.removeAllListeners('pageerror')
  page.removeAllListeners('framenavigated')
  page.on('pageerror', (error) => errors.push(error.message))
  const navigations = []
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame()) navigations.push(frame.url())
  })
  await page.goto(url, { waitUntil: 'networkidle' })
  await page.waitForTimeout(400)
  return navigations
}

async function expectStudio(page, label) {
  await page.waitForSelector('[data-testid="studio-landing"], [data-testid="studio-shell"]',
    { timeout: 15000 })
  assert.deepEqual(errors, [], `${label} 出现页面错误：${errors.join('; ')}`)
  assert.ok(!(await page.locator('.v3-root').count()), `${label} 仍渲染 V3 外壳`)
  assert.ok(!(await page.locator('.story-builder-page, .story-builder-empty').count()),
    `${label} 仍渲染 V2 面板`)
}

/** 归一化必须是 replaceState（不重新加载）：PerformanceNavigationTiming 只应有 1 条。 */
async function expectSingleDocumentLoad(page, label) {
  const navigations = await page.evaluate(
    () => window.performance.getEntriesByType('navigation').length)
  assert.equal(navigations, 1, `${label} 发生了页面重载（redirect loop）`)
}

;(async () => {
  const browser = await chromium.launch({ channel: 'msedge' })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })

  // 1) 默认入口 = Story Studio
  await open(page, `${BASE}/#/studio`)
  await expectStudio(page, '默认入口')

  // 2) ?ui=v3 → Story Studio（旧 V3 显式入口已移除）
  await open(page, `${BASE}/?ui=v3`)
  await expectStudio(page, '?ui=v3 入口')
  await expectSingleDocumentLoad(page, '?ui=v3 归一化')

  // 2b) #/v3 深链接 → Story Studio
  await open(page, `${BASE}/?ui=v3#/v3`)
  await expectStudio(page, '#/v3 深链接')

  // 2c) 裸 #/v3（无 query）→ Story Studio
  await open(page, `${BASE}/#/v3`)
  await expectStudio(page, '#/v3（无 query）')

  // 3) ?ui=v2 → Story Studio
  await open(page, `${BASE}/?ui=v2`)
  await expectStudio(page, '?ui=v2 入口')
  await expectSingleDocumentLoad(page, '?ui=v2 归一化')

  // 3b) #/story-builder 深链接 → Story Studio
  await open(page, `${BASE}/?ui=v2#/story-builder`)
  await expectStudio(page, '#/story-builder 深链接')

  // 4) 默认 URL 也不渲染任何旧外壳
  await open(page, `${BASE}/`)
  await expectStudio(page, '默认 URL')

  // 5) 旧 URL 归一化后 query 中的 ui 参数被清掉（书签自愈）
  await open(page, `${BASE}/?ui=v3&novel_id=studio_demo`)
  await expectStudio(page, '?ui=v3 + novel_id')
  const search = await page.evaluate(() => window.location.search)
  assert.ok(!search.includes('ui='), `归一化后仍保留 ui 参数：${search}`)
  assert.ok(search.includes('novel_id='), `归一化不得丢弃业务参数：${search}`)

  await browser.close()
  console.log('V4 legacy-entry fallback gate: PASS')
})().catch((error) => {
  console.error('V4 legacy-entry fallback gate: FAIL')
  console.error(error)
  process.exit(1)
})
