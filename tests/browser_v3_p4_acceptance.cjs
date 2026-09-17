// NovelForge V3-P4 Browser Acceptance：Outline & Chapter Workspace。
//
// 覆盖（V3 验收规范）：
//   空态（还没有大纲）· 真实四级结构（全书 / 卷 / 篇章 / 章纲）·
//   大纲缺口与警告 · Chapter Visual Entity · 章节 ContextPanel（role/Esc/焦点返回）·
//   唯一 Primary CTA · state A → 真实锻造 → state B（章节出现、结构更新）·
//   重新锻造入口 · Refresh / Deep-link · 四视口 ·
//   0 console error / 0 pageerror / 0 requestfailed / 0 非预期 4xx / 0 横向溢出。
//
// 运行前提（隔离数据根，不接触作者数据）：
//   .venv\Scripts\python.exe scripts/creator_ui_test_server.py --port 8030 --root workspace/v3_ui_test_root
//   node tests/browser_v3_p4_acceptance.cjs   （Playwright 自行安装：npm i -D playwright）
const { chromium, request } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const BASE = process.env.P4_BASE || 'http://127.0.0.1:8030'
const SHOTS = process.env.P4_SHOTS || 'workspace/product_v3/visual_review/audit'
const IDEA = '一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。'
const VIEWPORTS = [[1440, 1000], [1280, 900], [1024, 900], [390, 844]]

;(async () => {
  fs.mkdirSync(SHOTS, { recursive: true })
  const http = await request.newContext({ baseURL: BASE })
  const novelId = `novel_v3_p4_${Date.now() % 1000000}`

  // ---------------------------------------------------- state A：真实作品，还没有大纲
  assert.equal((await http.post('/api/story-builder/novels',
    { data: { novel_id: novelId, title: novelId } })).status(), 201)
  assert.equal((await http.put(`/api/story-builder/creative/brief?novel_id=${novelId}`,
    { data: { original_idea: IDEA, selected_genre: 'xianxia', tone: '紧张悬疑' } })).status(), 200)
  const seed = (await (await http.post(
    `/api/story-builder/settings/seed?novel_id=${novelId}`, { data: {} })).json()).seed
  assert.equal((await http.put(`/api/story-builder/settings/seed?novel_id=${novelId}`,
    { data: { seed, selected: seed.selected } })).status(), 200)
  assert.equal((await http.post(`/api/story-builder/runtime/start?novel_id=${novelId}`,
    { data: {} })).status(), 200)
  for (let index = 0; index < 6; index += 1) {
    const state = await (await http.get(
      `/api/story-builder/runtime/state?novel_id=${novelId}`)).json()
    const available = state.candidates.filter((row) => row.available).map((row) => row.action_id)
    if (!available.length) break
    await http.post(`/api/story-builder/runtime/advance?novel_id=${novelId}`,
      { data: { action_id: available[index % available.length], expected_revision: state.revision } })
  }

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
  page.on('requestfailed', (req) => failedRequests.push(
    `${phase}: ${req.method()} ${req.url()}`))
  page.on('response', (res) => {
    if (res.status() >= 400) {
      badResponses.push(`${phase}: ${res.status()} ${res.url().replace(BASE, '')}`)
    }
  })

  const load = async (hash) => {
    await page.goto(`${BASE}/?t=${Date.now()}${hash}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(900)
  }
  const outlineState = () => page.evaluate(() => {
    const levels = Array.from(document.querySelectorAll('[data-testid="v3-outline-levels"] li'))
      .map((row) => ({
        level: row.getAttribute('data-level'),
        empty: row.getAttribute('data-empty'),
        text: row.innerText,
      }))
    return {
      started: Boolean(document.querySelector('[data-testid="v3-outline-structure"]')),
      levels,
      gaps: Array.from(document.querySelectorAll('[data-testid="v3-outline-gaps"] li'))
        .map((row) => row.innerText),
      warnings: Array.from(document.querySelectorAll('[data-testid="v3-outline-warnings"] li'))
        .map((row) => row.innerText),
      volumes: document.querySelectorAll('[data-testid="v3-outline-volumes"] li').length,
      arcs: document.querySelectorAll('[data-testid="v3-outline-arcs"] li').length,
      chapters: document.querySelectorAll('.v3-workspace-view .v3-chapter').length,
      emptyState: Boolean(document.querySelector(
        '[data-testid="v3-view-chapters"] [data-testid="v3-empty-state"]')),
      primaryCtas: Array.from(document.querySelectorAll('.v3-workspace-view .v3-btn-primary'))
        .filter((node) => node.getBoundingClientRect().height > 0).length,
    }
  })
  const noOverflow = async (label) => {
    const size = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    assert.ok(size.scrollWidth <= size.clientWidth + 1,
      `${label}: 横向溢出 ${size.scrollWidth} > ${size.clientWidth}`)
  }

  try {
    // ---------------------------------------------------------- 空态：还没有大纲
    phase = 'outline-empty'
    await load(`#/n/${novelId}/outline`)
    await page.getByTestId('v3-view-chapters').waitFor({ timeout: 20000 })
    const before = await outlineState()
    assert.ok(before.emptyState, '没有大纲时必须显示空态，而不是空表')
    assert.equal(before.chapters, 0)
    assert.ok(before.gaps.length > 0 && /大纲/.test(before.gaps.join(' ')),
      `空态必须说明真实缺口：${before.gaps.join(' | ')}`)
    assert.equal(before.primaryCtas, 1, '空态只能有一个 Primary CTA')
    await page.locator('[data-testid="v3-rail"]').waitFor({ timeout: 10000 })
    assert.ok(await page.locator('[data-testid="v3-next-action-cta"].v3-btn-secondary')
      .isVisible(), '工作区已有主 CTA 时，右栏下一步必须降级为 secondary')
    const createCta = page.getByTestId('v3-chapter-create')
    assert.ok(await createCta.isVisible(), '空态必须给出锻造入口')
    await page.screenshot({ path: path.join(SHOTS, 'p4_outline_empty_1440.png'),
      fullPage: true })

    // ------------------------------- state A → 真实锻造 → state B（同一条深链接）
    phase = 'outline-forge'
    const forged = await http.post(`/api/story-builder/outline/forge?novel_id=${novelId}`,
      { data: { branch_id: 'main', volumes: 1, arcs_per_volume: 1, chapters_per_arc: 3 } })
    assert.equal(forged.status(), 200, await forged.text())
    await load(`#/n/${novelId}/outline`)
    await page.getByTestId('v3-outline-levels').waitFor({ timeout: 20000 })
    const after = await outlineState()
    assert.ok(after.chapters > 0, '锻造后必须出现真实章节')
    assert.ok(after.volumes > 0 && after.arcs > 0, '锻造后必须出现卷纲与篇章纲')
    assert.equal(after.levels.length, 4, '四级结构必须完整呈现')
    assert.ok(!after.levels.some((row) => row.level === 'book' && row.empty === 'true'),
      '锻造后全书主线不能再显示为缺失')
    assert.notDeepEqual(after.gaps, before.gaps,
      '锻造后缺口描述必须真实变化（不是同一段文案）')
    // 警告只在真实存在时出现（锻造质量报告 / 大纲自行声明的待办问题）。
    // 不允许为了「看起来有内容」而造警告：这里只断言不出现内部 code。
    for (const row of after.warnings) {
      assert.ok(!/[A-Z_]{6,}:/.test(row), `警告不得暴露内部 code：${row}`)
    }
    assert.equal(after.primaryCtas, 1, '已有大纲时仍然只能有一个 Primary CTA')
    assert.ok((await page.getByTestId('v3-outline-primary').innerText()).length > 0,
      '已有大纲时必须给出下一步入口')
    await page.screenshot({ path: path.join(SHOTS, 'p4_outline_structure_1440.png'),
      fullPage: true })

    // ------------------------------------------------ Chapter Visual Entity + 详情
    phase = 'chapter-detail'
    const firstChapter = page.locator('.v3-workspace-view .v3-chapter').first()
    const cardText = await firstChapter.innerText()
    assert.match(cardText, /第\s*\d+\s*章|章/, `章节卡必须有作者可读标题：${cardText}`)
    for (const banned of ['ol_forge', 'package_id', 'item_id']) {
      assert.ok(!cardText.includes(banned), `章节卡不得泄漏内部标识 ${banned}：${cardText}`)
    }
    // 章节摘要来自引擎原文，其中的行动 / 事件 id 必须已经翻成作者语言。
    assert.ok(!/(act_|ev_)[a-z0-9_]+/.test(cardText),
      `章节卡不得出现行动 / 事件 id：${cardText}`)
    await firstChapter.locator('.v3-card-hit').click()
    await page.getByTestId('v3-context-panel').waitFor({ timeout: 10000 })
    const panel = await page.evaluate(() => {
      const node = document.querySelector('[data-testid="v3-context-panel"]')
      const labelledby = node.getAttribute('aria-labelledby')
      const body = document.querySelector('[data-testid="v3-context-chapter"]')
      return {
        role: node.getAttribute('role'),
        labelledbyResolves: Boolean(labelledby && document.getElementById(labelledby)),
        focusInside: node.contains(document.activeElement),
        hasBody: Boolean(body),
        arc: body ? Boolean(body.querySelector('[data-testid="v3-context-chapter-arc"]')) : false,
        advancedCollapsed: !document.querySelector('[data-testid="v3-context-advanced"]')?.open,
        footer: (document.querySelector('[data-testid="v3-chapter-open-forge"]') || {})
          .innerText || '',
      }
    })
    assert.equal(panel.role, 'dialog')
    assert.ok(panel.labelledbyResolves && panel.focusInside)
    assert.ok(panel.hasBody, '章节详情必须展示这一章要达成什么 / 冲突')
    assert.ok(panel.arc, '章节详情必须说明它属于哪个篇章')
    assert.ok(panel.advancedCollapsed, '章纲包 / 条目 id 必须默认折叠')
    assert.ok(panel.footer.length > 0, '章节详情必须给出继续完善的入口')
    await page.screenshot({ path: path.join(SHOTS, 'p4_chapter_detail_1440.png') })
    await page.keyboard.press('Escape')
    await page.waitForTimeout(400)
    assert.ok(await page.evaluate(() => Boolean(
      document.activeElement.closest('.v3-chapter'))),
    '关闭后焦点必须回到章节卡片')

    // ------------------------------------------------- 重新锻造入口 + 刷新 / 深链接
    phase = 'outline-stale-entry'
    const advance = await http.get(`/api/story-builder/runtime/state?novel_id=${novelId}`)
    const runtimeState = await advance.json()
    const available = (runtimeState.candidates || []).filter((row) => row.available)
    if (available.length) {
      await http.post(`/api/story-builder/runtime/advance?novel_id=${novelId}`,
        { data: { action_id: available[0].action_id,
                  expected_revision: runtimeState.revision } })
      await load(`#/n/${novelId}/outline`)
      await page.getByTestId('v3-outline-stale').waitFor({ timeout: 20000 })
      assert.ok(await page.getByTestId('v3-outline-primary').isVisible(),
        '大纲过期时必须给出重新锻造入口')
      assert.ok((await page.getByTestId('v3-outline-primary').innerText()).includes('重新锻造'),
        '过期状态下主 CTA 必须说明要重新锻造')
      await page.screenshot({ path: path.join(SHOTS, 'p4_outline_stale_1440.png'),
        fullPage: true })
    }

    phase = 'outline-refresh'
    await page.reload({ waitUntil: 'networkidle' })
    await page.waitForTimeout(900)
    const restored = await outlineState()
    assert.ok(restored.chapters > 0, '刷新后必须恢复真实章节结构')
    assert.equal(restored.levels.length, 4)

    // --------------------------------------------------------------- 四视口
    for (const [width, height] of VIEWPORTS) {
      phase = `viewport:${width}`
      await page.setViewportSize({ width, height })
      await load(`#/n/${novelId}/outline`)
      await page.getByTestId('v3-outline-levels').waitFor({ timeout: 20000 })
      await noOverflow(`outline@${width}`)
      await page.screenshot({ path: path.join(SHOTS, `p4_outline_${width}.png`) })
    }

    assert.deepEqual(pageErrors, [], `pageerror：${pageErrors.join(' | ')}`)
    assert.deepEqual(failedRequests, [], `requestfailed：${failedRequests.join(' | ')}`)
    assert.deepEqual(consoleErrors, [], `console error：${consoleErrors.join(' | ')}`)
    assert.deepEqual(badResponses, [], `非预期 4xx/5xx：${badResponses.join(' | ')}`)
    console.log('PASS V3-P4 Acceptance：大纲空态 · 四级结构（全书/卷/篇章/章纲）· 缺口与警告 ·'
      + ' Chapter Visual Entity · 章节 ContextPanel（role/Esc/焦点返回/Advanced 折叠）·'
      + ' state A → 真实锻造 → state B · 重新锻造入口 · Refresh · 4 视口；'
      + '0 pageerror / 0 requestfailed / 0 console error / 0 非预期 4xx')
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(`FAIL ${error.message}\n${error.stack}`)
  process.exit(1)
})
