// NovelForge V3-P0 Browser Acceptance（Product Shell 稳定化门禁）。
//
// 覆盖 P0.1–P0.7：
//   Landing / 新建作品校验 / Command Center / 大纲工作区章节主链路
//   （列表 · 数量 · 空态 · 新建入口 · 点击详情 · 刷新与深链接恢复）
//   ContextPanel 可访问性（role/aria-modal/Esc/焦点进入/焦点陷阱/焦点返回）
//   高级工具 6 个关键页签（builder / guided / tree / outline / characters / inspector）
//   1440 / 1280 / 1024 / 390 无横向溢出
//   0 pageerror / 0 requestfailed / 0 未预期 console error / 0 非预期 4xx
//
// 运行前提（隔离数据根，不接触作者数据）：
//   .venv\Scripts\python.exe scripts/creator_ui_test_server.py --port 8030 --root workspace/v3_ui_test_root
//   node tests/browser_v3_p0_acceptance.cjs   （Playwright 自行安装：npm i -D playwright）
const { chromium } = require('playwright')
const assert = require('node:assert/strict')

const BASE = process.env.P0_BASE || 'http://127.0.0.1:8030'
const SHOTS = process.env.P0_SHOTS || 'workspace/product_v3/visual_review/audit'
/** 已经推演并锻造过章纲的作品（章节非空路径）。 */
const STARTED = process.env.P0_STARTED || 'novel_v3_accept_783716'
/** 没有构筑会话、没有章纲的作品（空态路径）。 */
const FRESH = process.env.P0_FRESH || 'audit_fmt_55126'
const VIEWPORTS = [[1440, 1000], [1280, 900], [1024, 900], [390, 844]]
const ADVANCED_TABS = ['builder', 'guided', 'tree', 'outline', 'characters', 'inspector']

const fs = require('node:fs')
const path = require('node:path')

async function panelAccessibility(page) {
  return page.evaluate(() => {
    const panel = document.querySelector('[data-testid="v3-context-panel"]')
    if (!panel) return { open: false }
    const labelledby = panel.getAttribute('aria-labelledby')
    return {
      open: true,
      role: panel.getAttribute('role'),
      ariaModal: panel.getAttribute('aria-modal'),
      labelledbyResolves: Boolean(labelledby && document.getElementById(labelledby)),
      focusInside: panel.contains(document.activeElement),
    }
  })
}

;(async () => {
  fs.mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const consoleErrors = []
  const pageErrors = []
  const badResponses = []
  const failedRequests = []
  let phase = 'init'
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(`${phase}: ${msg.text()}`)
  })
  page.on('pageerror', (error) => pageErrors.push(`${phase}: ${String(error)}`))
  page.on('requestfailed', (request) => {
    failedRequests.push(`${phase}: ${request.method()} ${request.url()} ` +
      `(${request.failure() ? request.failure().errorText : ''})`)
  })
  page.on('response', (response) => {
    if (response.status() >= 400) {
      badResponses.push(`${phase}: ${response.status()} ${response.url().replace(BASE, '')}`)
    }
  })

  const load = async (hash) => {
    await page.goto(`${BASE}/?t=${Date.now()}${hash}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(900)
  }
  const noOverflow = async (label) => {
    const size = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    assert.ok(size.scrollWidth <= size.clientWidth + 1,
      `${label}: 横向溢出 ${size.scrollWidth} > ${size.clientWidth}`)
  }

  try {
    // ------------------------------------------------------------ Landing
    phase = 'landing'
    await load('#/')
    await page.getByTestId('v3-landing').waitFor({ timeout: 20000 })
    const landing = await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll('.v3-novel-card'))
      const beyond = cards.map((card) => {
        const badge = card.querySelector('.v3-badge')
        const button = card.querySelector('.v3-novel-card-foot .v3-btn')
        const box = card.getBoundingClientRect()
        return Math.max(
          badge ? Math.round(badge.getBoundingClientRect().right - box.right) : 0,
          button ? Math.round(button.getBoundingClientRect().right - box.right) : 0)
      })
      return { cards: cards.length, worstBeyond: beyond.length ? Math.max(...beyond) : -99 }
    })
    assert.ok(landing.cards > 0, 'Landing 必须列出作品')
    assert.ok(landing.worstBeyond <= 0,
      `Landing 卡片内容越界 ${landing.worstBeyond}px（badge / 按钮必须留在卡片内）`)
    await page.screenshot({ path: path.join(SHOTS, 'p0_acceptance_landing.png') })

    // 新建作品：空提交必须被拦截，且不产生脏数据
    await page.getByTestId('v3-landing-new').click()
    await page.getByTestId('v3-landing-create-submit').click()
    await page.waitForTimeout(800)
    const validation = await page.evaluate(() => {
      const alert = document.querySelector('[role="alert"]')
      return { text: alert ? alert.textContent.trim() : '' }
    })
    assert.ok(validation.text.includes('作品编号'), `空提交必须给出校验提示，实际：${validation.text}`)
    await page.getByRole('button', { name: '取消' }).first().click()

    // ------------------------------------------------------ Command Center
    phase = 'command-center'
    await load(`#/n/${STARTED}`)
    await page.getByTestId('v3-command-center').waitFor({ timeout: 20000 })
    for (const testId of ['v3-novel-hero', 'v3-stage-track', 'v3-next-action-cta',
      'v3-current-objective-title']) {
      await page.getByTestId(testId).waitFor({ timeout: 10000 })
    }
    await page.screenshot({ path: path.join(SHOTS, 'p0_acceptance_command_center.png') })

    // 顶栏语义：Home = 当前作品总览
    const homeLabel = await page.getByTestId('v3-top-home').getAttribute('aria-label')
    assert.equal(homeLabel, '回到作品总览', `顶栏 Home 语义不一致：${homeLabel}`)
    await page.getByTestId('v3-top-home').click()
    await page.waitForTimeout(700)
    await page.getByTestId('v3-command-center').waitFor({ timeout: 10000 })

    // --------------------------------------------------- 大纲工作区：章节
    phase = 'outline-chapters'
    await load(`#/n/${STARTED}/outline`)
    await page.getByTestId('v3-view-chapters').waitFor({ timeout: 20000 })
    const chapters = await page.evaluate(() => ({
      cards: document.querySelectorAll('[data-testid^="v3-chapter-"]').length,
      heading: (document.querySelector('[data-testid="v3-view-chapters"] .v3-section-head') || {})
        .innerText || '',
      empty: Boolean(document.querySelector(
        '[data-testid="v3-view-chapters"] [data-testid="v3-empty-state"]')),
    }))
    assert.ok(chapters.cards > 0, '这本书应当有章节列表')
    assert.ok(!chapters.empty, '有章节时不应显示空态')
    assert.ok(/共 \d+ 章/.test(chapters.heading), `章节数量必须可见：${chapters.heading}`)
    await page.screenshot({ path: path.join(SHOTS, 'p0_acceptance_chapters.png'), fullPage: true })

    // 章节点击 → ContextPanel（可访问性契约）
    phase = 'chapter-dialog'
    await page.locator('[data-testid^="v3-chapter-"] .v3-card-hit').first().click()
    await page.getByTestId('v3-context-panel').waitFor({ timeout: 10000 })
    const dialog = await panelAccessibility(page)
    assert.equal(dialog.role, 'dialog', '章节详情必须是 role="dialog"')
    assert.equal(dialog.ariaModal, 'true', '章节详情必须声明 aria-modal')
    assert.ok(dialog.labelledbyResolves, 'aria-labelledby 必须指向真实标题')
    assert.ok(dialog.focusInside, '打开后焦点必须进入弹窗')
    let escaped = 0
    for (let index = 0; index < 12; index++) {
      await page.keyboard.press('Tab')
      const inside = await page.evaluate(() => {
        const panel = document.querySelector('[data-testid="v3-context-panel"]')
        return panel ? panel.contains(document.activeElement) : false
      })
      if (!inside) escaped++
    }
    assert.equal(escaped, 0, 'Tab 不得离开弹窗（焦点陷阱）')
    await page.keyboard.press('Escape')
    await page.waitForTimeout(400)
    const afterEsc = await page.evaluate(() => ({
      open: Boolean(document.querySelector('[data-testid="v3-context-panel"]')),
      focusOnChapter: Boolean(document.activeElement.closest('[data-testid^="v3-chapter-"]')),
    }))
    assert.equal(afterEsc.open, false, 'Esc 必须关闭弹窗')
    assert.ok(afterEsc.focusOnChapter, '关闭后焦点必须返回原触发元素')

    // 刷新与深链接恢复
    await page.reload({ waitUntil: 'networkidle' })
    await page.waitForTimeout(900)
    const restored = await page.evaluate(() => ({
      hash: location.hash,
      cards: document.querySelectorAll('[data-testid^="v3-chapter-"]').length,
    }))
    assert.ok(restored.hash.includes('/outline'), '刷新后必须保持在大纲工作区')
    assert.equal(restored.cards, chapters.cards, '刷新后章节数量必须一致')

    // ------------------------------------------------ 无章纲：空态 + 入口
    phase = 'chapters-empty'
    await load(`#/n/${FRESH}/outline`)
    await page.getByTestId('v3-view-chapters').waitFor({ timeout: 20000 })
    const empty = await page.evaluate(() => {
      const section = document.querySelector('[data-testid="v3-view-chapters"]')
      const cta = document.querySelector('[data-testid="v3-chapter-create"]')
      return {
        empty: Boolean(section && section.querySelector('[data-testid="v3-empty-state"]')),
        title: section && section.querySelector('.v3-empty h3')
          ? section.querySelector('.v3-empty h3').textContent : '',
        ctaVisible: cta ? cta.getBoundingClientRect().bottom <= window.innerHeight : false,
        ctaLabel: cta ? cta.innerText.trim() : '',
      }
    })
    assert.ok(empty.empty, '没有章纲时必须显示空态')
    assert.equal(empty.title, '还没有章节')
    assert.ok(empty.ctaVisible, '新建章节入口必须在首屏可达')
    await page.screenshot({ path: path.join(SHOTS, 'p0_acceptance_chapters_empty.png') })
    await page.getByTestId('v3-chapter-create').click()
    await page.waitForTimeout(1600)
    const forge = await page.evaluate(() => ({
      hash: location.hash,
      forgeVisible: document.body.innerText.includes('从剧情路线生成全书主线'),
    }))
    assert.equal(forge.hash.includes('tab=outline'), true, '新建入口必须打开大纲锻造')
    assert.ok(forge.forgeVisible, '新建入口必须真的打开锻造面板')

    // -------------------------------------------------------- 高级工具页签
    for (const tab of ADVANCED_TABS) {
      phase = `advanced:${tab}`
      await load(`#/story-builder?novel_id=${FRESH}&tab=${tab}`)
      const state = await page.evaluate((expected) => ({
        urlTab: new URLSearchParams(location.hash.split('?')[1] || '').get('tab'),
        groups: document.querySelectorAll('.creator-tab-group').length,
        onboarding: document.body.innerText.includes('从一个选择开始'),
        expected,
      }), tab)
      assert.equal(state.urlTab, tab, `${tab}: URL tab 未生效`)
      assert.equal(state.groups, 4, `${tab}: 高级工具页签栏缺失`)
      assert.ok(!state.onboarding, `${tab}: 仍然停在 onboarding`)
    }

    // ------------------------------------------------------------ 四视口
    for (const [width, height] of VIEWPORTS) {
      phase = `viewport:${width}`
      await page.setViewportSize({ width, height })
      await load('#/')
      await noOverflow(`landing@${width}`)
      await load(`#/n/${STARTED}`)
      await page.getByTestId('v3-command-center').waitFor({ timeout: 20000 })
      await noOverflow(`command-center@${width}`)
      await load(`#/n/${STARTED}/outline`)
      await page.getByTestId('v3-view-chapters').waitFor({ timeout: 20000 })
      await noOverflow(`outline@${width}`)
      await page.screenshot({ path: path.join(SHOTS, `p0_acceptance_outline_${width}.png`) })
      if (width <= 1024) {
        await page.getByTestId('v3-rail-toggle').click()
        await page.waitForTimeout(400)
        await page.keyboard.press('Escape')
        await page.waitForTimeout(300)
        assert.ok(!(await page.getByTestId('v3-rail').isVisible()),
          `${width}px: Esc 必须收起目标抽屉`)
      }
    }

    assert.deepEqual(pageErrors, [], `pageerror：${pageErrors.join(' | ')}`)
    assert.deepEqual(failedRequests, [], `requestfailed：${failedRequests.join(' | ')}`)
    assert.deepEqual(consoleErrors, [], `console error：${consoleErrors.join(' | ')}`)
    assert.deepEqual(badResponses, [], `非预期 4xx/5xx：${badResponses.join(' | ')}`)
    console.log('PASS V3-P0 Acceptance：Landing / 新建作品 / Command Center / '
      + '章节主链路（列表·数量·空态·入口·详情） / ContextPanel a11y / '
      + `${ADVANCED_TABS.length} 个高级工具页签 / ${VIEWPORTS.length} 个视口；`
      + '0 pageerror / 0 requestfailed / 0 console error / 0 非预期 4xx')
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(`FAIL ${error.message}`)
  process.exit(1)
})
