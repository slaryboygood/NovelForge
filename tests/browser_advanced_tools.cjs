// NovelForge Phase 1 回归：高级工具必须真正可达。
//
// 覆盖：
//   1. 19 个 V2 高级工具页签：URL tab 生效、页签栏存在、命中对应面板、不是 onboarding；
//   2. 没有构筑会话的作品同样可用（这是合法业务状态，不是错误）；
//   3. V3「展开的工具」入口真正落到目标面板；
//   4. 1440 / 1280 / 1024 / 390 无横向溢出；
//   5. 0 console error / 0 pageerror / 0 非预期 HTTP 4xx。
//
// 运行前提（隔离数据根，不接触作者数据）：
//   .venv\Scripts\python.exe scripts/creator_ui_test_server.py --port 8030 --root workspace/v3_ui_test_root
//   node tests/browser_advanced_tools.cjs   （Playwright 自行安装：npm i -D playwright）
const { chromium } = require('playwright')
const assert = require('node:assert/strict')

const BASE = process.env.P1_BASE || 'http://127.0.0.1:8030'
const NOVEL = process.env.P1_NOVEL || 'audit_fmt_55126'
const SHOTS = process.env.P1_SHOTS || 'workspace/product_v3/visual_review/audit'

const TAB_LABELS = {
  guided: '引导流', builder: '故事构筑', overview: '设定总览', mood: '风格参考位',
  world: '世界面板', characters: '角色面板', plot: '剧情面板', progression: '成长面板',
  memory: '记忆面板', director: '导演面板', regions: '区域卡片', relations: '关系网',
  route: '路线实验室', outline: '大纲锻造', linkage: '大纲联动', compare: '路线对比',
  tree: '大纲结构树', inspector: 'Canon 检查器', repair: '修复中心',
}

// V3 工作区 → 展开的工具 → 期望落到的页签
const V3_TOOL_ENTRIES = [
  ['outline', '大纲锻造', 'outline'],
  ['outline', '大纲结构树', 'tree'],
  ['outline', '大纲联动', 'linkage'],
  ['world', '世界面板', 'world'],
  ['world', '区域卡片', 'regions'],
  ['characters', '角色面板', 'characters'],
  ['review', 'Canon 检查器', 'inspector'],
  ['review', '修复中心', 'repair'],
]

const VIEWPORTS = [
  { name: '1440', width: 1440, height: 1000 },
  { name: '1280', width: 1280, height: 900 },
  { name: '1024', width: 1024, height: 900 },
  { name: '390', width: 390, height: 844 },
]

;(async () => {
  const fs = require('node:fs')
  fs.mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const consoleErrors = []
  const pageErrors = []
  const badResponses = []
  let phase = 'init'
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(`${phase}: ${msg.text()}`)
  })
  page.on('pageerror', (error) => pageErrors.push(`${phase}: ${String(error)}`))
  page.on('response', (response) => {
    if (response.status() >= 400) {
      badResponses.push(`${phase}: ${response.status()} ${response.url().replace(BASE, '')}`)
    }
  })

  /** 每次都做整页加载：hash-only 导航在崩溃后不会重新渲染，会掩盖问题。 */
  const load = async (hash) => {
    await page.goto(`${BASE}/?t=${Date.now()}${hash}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(900)
  }

  try {
    // ---------------------------------------------------------- 1 全部页签
    for (const [tab, label] of Object.entries(TAB_LABELS)) {
      phase = `tab:${tab}`
      await load(`#/story-builder?novel_id=${NOVEL}&tab=${tab}`)
      const state = await page.evaluate((expected) => ({
        urlTab: new URLSearchParams(location.hash.split('?')[1] || '').get('tab'),
        groups: document.querySelectorAll('.creator-tab-group').length,
        buttons: document.querySelectorAll('.creator-tabs button').length,
        activeTab: document.querySelector('[aria-selected="true"]')?.textContent?.trim() ?? '',
        onboarding: document.body.innerText.includes('从一个选择开始'),
        boundary: Boolean(document.querySelector('[data-testid="panel-boundary-error"]')),
        textLength: document.body.innerText.length,
        expected,
      }), label)
      assert.equal(state.urlTab, tab, `${tab}: URL tab 参数没有生效`)
      assert.equal(state.groups, 4, `${tab}: 页签分组缺失（高级工具 Shell 必须照常渲染）`)
      assert.equal(state.buttons, 19, `${tab}: 页签按钮数量不足（高级工具不可达）`)
      assert.equal(state.activeTab, label, `${tab}: 当前页签不是 ${label}`)
      assert.ok(!state.onboarding, `${tab}: 仍然停在 onboarding 页面`)
      assert.ok(!state.boundary, `${tab}: 面板渲染失败（见 data-testid="panel-boundary-error"）`)
      assert.ok(state.textLength > 400, `${tab}: 面板内容为空`)
      await page.screenshot({ path: `${SHOTS}/p1_regress_${tab}.png` })
    }

    // ------------------------------------- 2 没有会话也能新建小说 / 建立会话
    phase = 'init-state'
    await load(`#/story-builder?novel_id=${NOVEL}&tab=builder`)
    for (const testId of ['story-builder-init', 'story-builder-init-start',
      'story-builder-new-novel-id', 'story-builder-new-pack']) {
      await page.getByTestId(testId).waitFor({ timeout: 10000 })
    }

    // ------------------------------------------- 3 V3「展开的工具」真正落地
    for (const [view, label, expectedTab] of V3_TOOL_ENTRIES) {
      phase = `v3-tool:${view}/${label}`
      await load(`#/n/${NOVEL}/${view}`)
      const entry = page.locator('[data-testid="v3-view-tools"] button', { hasText: label }).first()
      assert.equal(await entry.count(), 1, `${view}: 找不到工具入口 ${label}`)
      await entry.click()
      await page.waitForTimeout(1500)
      const landed = await page.evaluate(() => ({
        tab: new URLSearchParams(location.hash.split('?')[1] || '').get('tab'),
        onboarding: document.body.innerText.includes('从一个选择开始'),
        boundary: Boolean(document.querySelector('[data-testid="panel-boundary-error"]')),
      }))
      assert.equal(landed.tab, expectedTab, `${label}: 落到的页签不是 ${expectedTab}`)
      assert.ok(!landed.onboarding, `${label}: 落到了 onboarding，而不是目标面板`)
      assert.ok(!landed.boundary, `${label}: 目标面板渲染失败`)
      await page.screenshot({ path: `${SHOTS}/p1_regress_v3tool_${label}.png` })
    }

    // ------------------------------------------------- 4 四视口无横向溢出
    for (const viewport of VIEWPORTS) {
      phase = `viewport:${viewport.name}`
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await load(`#/story-builder?novel_id=${NOVEL}&tab=tree`)
      const overflow = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }))
      assert.ok(overflow.scrollWidth <= overflow.clientWidth + 1,
        `${viewport.name}px: 出现横向溢出 ${overflow.scrollWidth} > ${overflow.clientWidth}`)
      await page.screenshot({ path: `${SHOTS}/p1_regress_vp_${viewport.name}.png` })
    }

    assert.deepEqual(pageErrors, [], `存在 pageerror：${pageErrors.join(' | ')}`)
    assert.deepEqual(consoleErrors, [], `存在 console error：${consoleErrors.join(' | ')}`)
    assert.deepEqual(badResponses, [], `存在非预期 HTTP 4xx/5xx：${badResponses.join(' | ')}`)
    console.log(`PASS 高级工具回归：${Object.keys(TAB_LABELS).length} 个页签 + `
      + `${V3_TOOL_ENTRIES.length} 个 V3 工具入口 + ${VIEWPORTS.length} 个视口，`
      + '0 console error / 0 pageerror / 0 4xx')
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(`FAIL ${error.message}`)
  process.exit(1)
})
