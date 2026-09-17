// NovelForge V3-P3 Browser Acceptance：Story Simulation Workspace。
//
// 覆盖（V3 验收规范）：
//   进入推演 Workspace · 无 runtime 的空态 · 有推演状态时的 Route Candidates ·
//   Route 点击 ContextPanel · 真实推演执行 → Result Feedback → Objective / NextAction 更新 ·
//   Refresh 恢复 · Deep-link 恢复 · Advanced RouteLab bridge · 四视口 · 唯一 Primary CTA ·
//   0 console error / 0 pageerror / 0 requestfailed / 0 非预期 4xx / 0 横向溢出。
//
// 运行前提（隔离数据根，不接触作者数据）：
//   .venv\Scripts\python.exe scripts/creator_ui_test_server.py --port 8030 --root workspace/v3_ui_test_root
//   node tests/browser_v3_p3_acceptance.cjs   （Playwright 自行安装：npm i -D playwright）
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const BASE = process.env.P3_BASE || 'http://127.0.0.1:8030'
const SHOTS = process.env.P3_SHOTS || 'workspace/product_v3/visual_review/audit'
/** 已经开始推演的作品（有真实候选方向）。 */
const STARTED = process.env.P3_NOVEL || 'novel_v3_accept_783716'
/** 没有构筑会话的作品（空态路径）。 */
const FRESH = process.env.P3_FRESH || 'audit_fmt_55126'
const VIEWPORTS = [[1440, 1000], [1280, 900], [1024, 900], [390, 844]]

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
  page.on('requestfailed', (request) => failedRequests.push(
    `${phase}: ${request.method()} ${request.url()}`))
  page.on('response', (response) => {
    if (response.status() >= 400) {
      badResponses.push(`${phase}: ${response.status()} ${response.url().replace(BASE, '')}`)
    }
  })

  const load = async (hash) => {
    await page.goto(`${BASE}/?t=${Date.now()}${hash}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(900)
  }
  const situation = () => page.evaluate(() => ({
    heading: (document.querySelector('[data-testid="v3-simulation-situation"] .v3-section-head')
      || {}).innerText || '',
    summary: (document.querySelector('[data-testid="v3-simulation-summary"]') || {})
      .textContent || '',
    branches: document.querySelectorAll('[data-testid="v3-simulation-branches"] li').length,
    candidates: document.querySelectorAll('[data-testid^="v3-route-"]:not([data-testid*="visual"]):not([data-testid*="pick"])').length,
    primaryCtas: Array.from(document.querySelectorAll('.v3-workspace-view .v3-btn-primary'))
      .filter((node) => node.getBoundingClientRect().height > 0).length,
  }))
  const noOverflow = async (label) => {
    const size = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    assert.ok(size.scrollWidth <= size.clientWidth + 1,
      `${label}: 横向溢出 ${size.scrollWidth} > ${size.clientWidth}`)
  }

  try {
    // ------------------------------------------------ 空态：还不能推演
    phase = 'simulation-empty'
    await load(`#/n/${FRESH}/simulation`)
    await page.getByTestId('v3-simulation-situation').waitFor({ timeout: 20000 })
    const empty = await page.evaluate(() => {
      const section = document.querySelector('[data-testid="v3-simulation-situation"]')
      const cta = document.querySelector('[data-testid="v3-simulation-empty-cta"]')
      return {
        empty: Boolean(section.querySelector('[data-testid="v3-empty-state"]')),
        title: section.querySelector('.v3-empty h3').textContent,
        reason: section.querySelector('.v3-empty p').textContent,
        ctaLabel: cta ? cta.innerText.trim() : '',
        ctaVisible: cta ? cta.getBoundingClientRect().bottom <= window.innerHeight : false,
        routesSection: Boolean(document.querySelector('[data-testid="v3-simulation-routes"]')),
      }
    })
    assert.ok(empty.empty, '不能推演时必须显示空态而不是空表')
    assert.match(empty.title, /推演/)
    assert.ok(empty.reason.length > 6, '空态必须解释真实原因')
    assert.ok(empty.ctaVisible, '空态 CTA 必须在首屏可达')
    assert.ok(!empty.routesSection, '不能推演时不得渲染空的路线区块')
    await page.screenshot({ path: path.join(SHOTS, 'p3_simulation_empty_1440.png') })

    // ------------------------------------------- 有推演状态：候选 + 唯一 CTA
    phase = 'simulation-routes'
    await load(`#/n/${STARTED}/simulation`)
    await page.getByTestId('v3-simulation-routes').waitFor({ timeout: 20000 })
    const before = await situation()
    assert.ok(before.candidates > 0, '有推演状态时必须列出真实候选方向')
    assert.ok(before.branches > 0, '必须显示当前路线')
    assert.equal(before.primaryCtas, 1, '推演工作区只能有一个 Primary CTA')
    assert.ok(/第 \d+ 回合/.test(before.heading), `状况卡必须说明回合：${before.heading}`)
    await page.screenshot({ path: path.join(SHOTS, 'p3_simulation_routes_1440.png'),
      fullPage: true })

    // ------------------------------------- P3 CLOSEOUT：V3 Native 路线比较
    phase = 'simulation-compare'
    const compareIds = await page.evaluate(() => Array.from(
      document.querySelectorAll('[data-testid^="v3-route-compare-"]'))
      .slice(0, 2).map((node) => node.getAttribute('data-testid')))
    assert.ok(compareIds.length >= 2, '需要至少两条路线才能比较')
    for (const testId of compareIds) {
      await page.getByTestId(testId).click()
      await page.waitForTimeout(300)
    }
    await page.getByTestId('v3-simulation-comparison').waitFor({ timeout: 10000 })
    const comparison = await page.evaluate(() => {
      const section = document.querySelector('[data-testid="v3-simulation-comparison"]')
      const rows = Array.from(section.querySelectorAll('.v3-compare-rows li'))
      return {
        heading: section.querySelector('.v3-section-head').innerText,
        columns: section.querySelectorAll('.v3-compare-head b').length,
        rows: rows.length,
        diffRows: rows.filter((row) => row.classList.contains('is-diff')).length,
        note: Boolean(section.querySelector('.v3-compare-note')),
        text: section.innerText,
        primaryCtas: Array.from(document.querySelectorAll('.v3-workspace-view .v3-btn-primary'))
          .filter((node) => node.getBoundingClientRect().height > 0).length,
      }
    })
    assert.equal(comparison.columns, 2, '比较必须同时显示两条路线')
    assert.ok(comparison.rows > 0, '比较必须给出真实维度')
    assert.ok(comparison.diffRows > 0 || comparison.note,
      '有差异就标出差异；没有真实差异必须说明，而不是造差异')
    for (const banned of ['branch_id', 'runtime_id', 'score', 'weights', '{', '}']) {
      assert.ok(!comparison.text.includes(banned),
        `比较区不得暴露内部字段 ${banned}`)
    }
    assert.equal(comparison.primaryCtas, 1, '比较不改变唯一 Primary CTA')
    await page.screenshot({ path: path.join(SHOTS, 'p3_simulation_compare_1440.png'),
      fullPage: true })
    await page.getByTestId('v3-compare-close').click()
    await page.waitForTimeout(300)

    // --------------------------------------------- Route 点击 → ContextPanel
    phase = 'simulation-route-panel'
    await page.locator('[data-testid^="v3-route-"]:not([data-testid*="visual"]):not([data-testid*="pick"]) .v3-card-hit')
      .first().click()
    await page.getByTestId('v3-context-panel').waitFor({ timeout: 10000 })
    const panel = await page.evaluate(() => {
      const node = document.querySelector('[data-testid="v3-context-panel"]')
      const labelledby = node.getAttribute('aria-labelledby')
      return {
        role: node.getAttribute('role'),
        labelledbyResolves: Boolean(labelledby && document.getElementById(labelledby)),
        focusInside: node.contains(document.activeElement),
        routeBody: Boolean(document.querySelector('[data-testid="v3-context-route"]')),
        advancedCollapsed: !document.querySelector('[data-testid="v3-context-advanced"]')?.open,
        footer: (document.querySelector('[data-testid="v3-route-advance"]') || {}).innerText || '',
        details: Array.from(document.querySelectorAll(
          '[data-testid="v3-context-route"] .v3-context-evidence li'))
          .map((row) => row.innerText).join(' | '),
      }
    })
    assert.equal(panel.role, 'dialog')
    assert.ok(panel.labelledbyResolves && panel.focusInside)
    assert.ok(panel.routeBody, '路线详情必须展示方向 / 条件 / 代价')
    assert.ok(panel.advancedCollapsed, 'raw branch / weights 必须默认折叠')
    assert.ok(panel.footer.length > 0, '路线详情必须给出推演动作')
    // 作者语言：条件 / 代价必须是可读句子，不能把内部 key 直接抛给作者。
    for (const banned of ['core_record', 'start_place', 'work_place', 'act_',
      'branch_id', 'runtime_id', 'weight']) {
      assert.ok(!panel.details.includes(banned),
        `路线详情不得暴露内部标识 ${banned}：${panel.details}`)
    }
    // P3 CLOSEOUT：世界影响（地点 / 势力）必须在路线详情里可见。
    // 只有当这条作品真的存在实体引用时才断言内容，不制造假影响对象。
    const worldImpact = await page.evaluate(async () => {
      const novelId = (location.hash.match(/#\/n\/([^/?]+)/) || [])[1] || ''
      const payload = await (await fetch(
        `/api/story-builder/v3/novels/${novelId}/command-center`)).json()
      const withImpact = (payload.simulation?.candidates || []).find((row) => (
        (row.affected_locations || []).length + (row.affected_factions || []).length) > 0)
      if (!withImpact) return { required: false }
      return {
        required: true,
        candidateId: withImpact.candidate_id,
        locations: withImpact.affected_locations || [],
        factions: withImpact.affected_factions || [],
      }
    })
    if (worldImpact.required) {
      await page.keyboard.press('Escape')
      await page.waitForTimeout(400)
      await page.getByTestId(`v3-route-${worldImpact.candidateId}`).click()
      await page.getByTestId('v3-context-panel').waitFor({ timeout: 10000 })
      const impactText = await page.evaluate(() => ({
        locations: (document.querySelector('[data-testid="v3-context-route-locations"]')
          || {}).textContent || '',
        factions: (document.querySelector('[data-testid="v3-context-route-factions"]')
          || {}).textContent || '',
        panel: (document.querySelector('[data-testid="v3-context-route"]') || {})
          .innerText || '',
      }))
      for (const name of worldImpact.locations) {
        assert.ok(impactText.locations.includes(name),
          `路线详情必须显示真实受影响地点「${name}」：${impactText.panel}`)
      }
      for (const name of worldImpact.factions) {
        assert.ok(impactText.factions.includes(name),
          `路线详情必须显示真实受影响势力「${name}」：${impactText.panel}`)
      }
      await page.screenshot({
        path: path.join(SHOTS, 'p3_simulation_world_impact_1440.png') })
      await page.keyboard.press('Escape')
      await page.waitForTimeout(400)
      await page.locator('[data-testid^="v3-route-"]:not([data-testid*="visual"]):not([data-testid*="pick"]) .v3-card-hit')
        .first().click()
      await page.getByTestId('v3-context-panel').waitFor({ timeout: 10000 })
    }
    await page.screenshot({ path: path.join(SHOTS, 'p3_simulation_selected_route_1440.png') })
    await page.keyboard.press('Escape')
    await page.waitForTimeout(400)
    assert.ok(await page.evaluate(() => Boolean(
      document.activeElement.closest('[data-testid^="v3-route-"]'))),
    '关闭后焦点必须回到路线卡片')

    // ------------------------------------------- 真实推演 → Result Feedback
    phase = 'simulation-advance'
    await page.getByTestId('v3-simulation-advance').click()
    await page.getByTestId('v3-simulation-feedback').waitFor({ timeout: 60000 })
    const feedback = await page.evaluate(() => ({
      title: (document.querySelector('[data-testid="v3-simulation-feedback"] b') || {})
        .textContent || '',
      lines: Array.from(document.querySelectorAll(
        '[data-testid="v3-simulation-feedback"] li')).map((row) => row.textContent),
      heading: (document.querySelector('[data-testid="v3-simulation-situation"] .v3-section-head')
        || {}).innerText || '',
    }))
    assert.match(feedback.title, /推演/, `推演反馈标题异常：${feedback.title}`)
    assert.ok(feedback.lines.length >= 2,
      `反馈必须说明发生了什么（回合 / 目标 / 下一步）：${feedback.lines.join(' | ')}`)
    assert.ok(feedback.lines.some((line) => line.includes('回合')),
      '反馈必须给出真实的回合变化')
    const feedbackText = [feedback.title, ...feedback.lines].join(' ')
    for (const banned of ['act_', 'ev_', 'branch_id', 'runtime_id', 'score']) {
      assert.ok(!feedbackText.includes(banned),
        `推演反馈必须是作者语言，不得出现内部 id（${banned}）：${feedbackText}`)
    }
    assert.ok(!feedback.title.includes('没有执行'),
      `推演必须真的成功：${feedback.lines.join(' | ')}`)
    const afterAdvance = await situation()
    assert.notEqual(afterAdvance.heading, before.heading,
      '推演后当前故事状况必须更新（tick/revision 真实变化）')
    await page.screenshot({ path: path.join(SHOTS, 'p3_simulation_result_1440.png'),
      fullPage: true })

    // Refresh restore：真实状态必须保留
    phase = 'simulation-refresh'
    await page.reload({ waitUntil: 'networkidle' })
    await page.waitForTimeout(900)
    const restored = await situation()
    assert.equal(restored.heading, afterAdvance.heading, '刷新后必须保留推演后的状态')
    assert.ok(restored.candidates > 0)

    // Deep-link restore
    phase = 'simulation-deeplink'
    await load(`#/n/${STARTED}/simulation`)
    assert.ok(await page.evaluate(() => Boolean(
      document.querySelector('[data-testid="v3-simulation-routes"]'))),
    '深链接必须直接恢复推演工作区')

    // Advanced RouteLab bridge
    phase = 'simulation-advanced-bridge'
    await page.getByTestId('v3-tool-route').click()
    await page.waitForTimeout(1500)
    const bridge = await page.evaluate(() => ({
      hash: location.hash,
      legacy: Boolean(document.querySelector('[data-testid="legacy-back-to-v3"]')),
    }))
    assert.ok(bridge.hash.includes('tab=route'), `RouteLab bridge 目标错误：${bridge.hash}`)
    assert.ok(bridge.legacy, 'RouteLab bridge 必须打开既有路线实验室')

    // ---------------------------------------------------------- 四视口
    for (const [width, height] of VIEWPORTS) {
      phase = `viewport:${width}`
      await page.setViewportSize({ width, height })
      await load(`#/n/${STARTED}/simulation`)
      await noOverflow(`simulation@${width}`)
      await page.screenshot({ path: path.join(SHOTS, `p3_simulation_${width}.png`) })
    }

    assert.deepEqual(pageErrors, [], `pageerror：${pageErrors.join(' | ')}`)
    assert.deepEqual(failedRequests, [], `requestfailed：${failedRequests.join(' | ')}`)
    assert.deepEqual(consoleErrors, [], `console error：${consoleErrors.join(' | ')}`)
    assert.deepEqual(badResponses, [], `非预期 4xx/5xx：${badResponses.join(' | ')}`)
    console.log('PASS V3-P3 Acceptance：推演空态 · Route Candidates · Route ContextPanel'
      + '（role/Esc/焦点返回/Advanced 折叠）· 真实推演 → Result Feedback → 状况更新 ·'
      + ` Refresh / Deep-link / RouteLab bridge · ${VIEWPORTS.length} 视口；`
      + '0 pageerror / 0 requestfailed / 0 console error / 0 非预期 4xx')
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(`FAIL ${error.message}`)
  process.exit(1)
})
