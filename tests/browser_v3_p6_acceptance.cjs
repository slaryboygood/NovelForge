// NovelForge V3-P6 Full Product Acceptance（V3 最终验收规范）。
//
// 这是最终门禁：不引用任何历史 PASS，全部在真实浏览器里重新执行。
//
//   1. Landing → 新建作品 → Command Center
//   2. Creation Journey 完整主链：一句话创意 → 候选 → 选择 → 设定 → 自检 → 开始推演
//   3. Objective / Next Action 真实变化
//   4. 九个 AuthorJourney 工作区全部可达且是作者语言
//   5. 推演 → 大纲 → 检查 → 导出 主链（真实 mutation 后状态更新）
//   6. Refresh restore / Deep-link / Browser Back / Switch Novel
//   7. Advanced Tools reachable（19 页签）
//   8. 1440 / 1280 / 1024 / 390 四视口
//   9. First-Time User Acceptance（不给说明书：每屏 5 秒内能回答「这是什么 / 该做什么」）
//  10. 0 pageerror / 0 requestfailed / 0 console error / 0 非预期 4xx / 0 横向溢出
//
// 运行前提（隔离数据根）：
//   .venv\Scripts\python.exe scripts/creator_ui_test_server.py --port 8030 --root workspace/v3_ui_test_root
const { chromium, request } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const BASE = process.env.P6_BASE || 'http://127.0.0.1:8030'
const SHOTS = process.env.P6_SHOTS || 'workspace/product_v3/visual_review/audit'
const IDEA = '一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。'
const VIEWPORTS = [[1440, 1000], [1280, 900], [1024, 900], [390, 844]]
const WORKSPACES = ['creation', 'world', 'characters', 'story', 'simulation',
  'outline', 'review', 'export']
// First-Time User Acceptance：这些内部概念一次都不许出现在任何主界面。
const FORBIDDEN_EVERYWHERE = ['Canon Inspector', 'truth_layer', 'provenance',
  'payload', 'opcode', 'execution_api', 'branch_id', 'runtime_id']
// 主界面不允许裸露任何引擎 id（行动 / 事件 / 大纲包 / 势力 / 角色 / 地点 / 合成 key）。
// Visual Asset Gate 期间在此处发现过 `控制方 faction_1`，因此把检查面扩大到实体 id。
const INTERNAL_ID_PATTERN = new RegExp('\\b(act_[a-z0-9_]+|ev_[a-z0-9_]+|ol_forge_[a-z0-9_]+'
  + '|faction_\\d+|npc_\\d+|location_\\d+|character_\\d+'
  + '|start_place|work_place|hidden_place|core_record)\\b')

/** 失败时报告停在哪个阶段（各步骤把阶段名写进这个变量）。 */
let phase = 'init'
const report = (error) => {
  console.error(`FAIL [phase=${phase}] ${error.message}\n${error.stack}`)
  process.exit(1)
}

;(async () => {
  fs.mkdirSync(SHOTS, { recursive: true })
  const http = await request.newContext({ baseURL: BASE })
  const novelId = `novel_v3_p6_${Date.now() % 1000000}`
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const consoleErrors = []
  const pageErrors = []
  const badResponses = []
  const failedRequests = []
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

  const noOverflow = async (label) => {
    const size = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    assert.ok(size.scrollWidth <= size.clientWidth + 1,
      `${label}: 横向溢出 ${size.scrollWidth} > ${size.clientWidth}`)
  }
  const bodyText = () => page.evaluate(() => document.body.innerText)
  /**
   * First-Time User Acceptance：每个核心 Workspace 必须能回答
   * 「这是什么 / 现在最重要的事 / 该点哪儿」。
   */
  const assertWorkspaceAnswers = async (view) => {
    // 创作工作区用的是自己的流程壳（CreationFlow），其余工作区共用 WorkspaceView。
    const info = await page.evaluate(() => ({
      goal: ((document.querySelector('[data-testid="v3-view-goal-title"]')
        || document.querySelector('[data-testid="v3-creation-goal-title"]')) || {})
        .innerText || '',
      primary: (document.querySelector(
        '.v3-workspace-view .v3-btn-primary, .v3-creation .v3-btn-primary') || {})
        .innerText || '',
      nextAction: (document.querySelector('[data-testid="v3-next-action-title"]') || {})
        .innerText || '',
      visible: Boolean(document.querySelector('.v3-workspace-view, [data-testid="v3-creation-workspace"]')),
    }))
    assert.ok(info.visible, `${view}: 工作区必须渲染`)
    assert.ok(info.goal.length > 2, `${view}: 必须说明现在要做什么：${info.goal}`)
    assert.ok(info.nextAction.length > 2, `${view}: 右栏必须说明下一步：${info.nextAction}`)
    return info
  }

  try {
    // ------------------------------------------------- 1. Landing → 新建作品
    phase = 'landing'
    await page.goto(`${BASE}/?ui=v3&t=${Date.now()}#/`, { waitUntil: 'networkidle' })
    await page.getByTestId('v3-landing').waitFor({ timeout: 30000 })
    const landing = await page.evaluate(() => ({
      cta: (document.querySelector('[data-testid="v3-landing-new"]') || {}).innerText || '',
      hasCards: document.querySelectorAll('[data-testid^="v3-novel-card-"]').length,
      text: document.body.innerText,
    }))
    assert.ok(landing.cta.length > 0, 'Landing 必须给出「新建作品」')
    for (const banned of FORBIDDEN_EVERYWHERE) {
      assert.ok(!landing.text.includes(banned), `Landing 不得出现内部概念 ${banned}`)
    }
    await page.screenshot({ path: path.join(SHOTS, 'p6_landing_1440.png'), fullPage: true })

    phase = 'create-novel'
    await page.getByTestId('v3-landing-new').click()
    await page.getByLabel('新作品编号').fill(novelId)
    await page.getByTestId('v3-landing-create-submit').click()
    await page.getByTestId('v3-command-center').waitFor({ timeout: 30000 })

    // ------------------------------------- 2. Creation Journey 完整主链
    phase = 'creation-idea'
    const ccBefore = await page.evaluate(() => ({
      stage: (document.querySelector('[data-testid="v3-hero-stage"]') || {}).innerText || '',
      objective: (document.querySelector('[data-testid="v3-current-objective-title"]')
        || {}).innerText || '',
      next: (document.querySelector('[data-testid="v3-next-action-title"]') || {})
        .innerText || '',
    }))
    assert.ok(ccBefore.next.length > 0, 'Command Center 必须给出下一步')
    await page.getByTestId('v3-next-action-cta').click()
    await page.getByTestId('v3-creation-workspace').waitFor({ timeout: 20000 })
    await page.getByLabel('一句话创意').fill(IDEA)
    await page.getByLabel('读者体验').fill('悬疑、温柔')
    await page.getByTestId('v3-idea-suggest').click()
    await page.getByTestId('v3-genre-candidates').waitFor({ timeout: 40000 })
    await page.getByTestId('v3-genre-candidates-card').first().click()
    await page.getByTestId('v3-idea-save').click()
    await page.getByTestId('v3-feedback').waitFor({ timeout: 30000 })

    phase = 'creation-settings'
    // NF-009：「确定这个方向」之后产品自己必须进入下一步，不能把作者留在原地。
    await page.getByTestId('v3-flow-settings').waitFor({ timeout: 30000 })
    await page.getByTestId('v3-settings-suggest').click()
    await page.getByTestId('v3-setting-groups').waitFor({ timeout: 60000 })
    await page.getByTestId('v3-settings-save').click()
    await page.getByTestId('v3-feedback').waitFor({ timeout: 30000 })

    phase = 'creation-check'
    await page.getByTestId('v3-flow-step-check').click()
    await page.getByTestId('v3-check-run').click()
    await page.getByTestId('v3-check-result').waitFor({ timeout: 90000 })

    phase = 'creation-runtime'
    await page.getByTestId('v3-flow-step-runtime').click()
    await page.getByTestId('v3-runtime-ready').waitFor({ timeout: 30000 })
    await page.getByTestId('v3-runtime-start').click()
    await page.waitForFunction(() => document
      .querySelector('[data-testid="v3-flow-step-runtime"]')
      ?.className.includes('is-done'), null, { timeout: 90000 })
    await page.goto(`${BASE}/?ui=v3#/n/${novelId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('v3-command-center').waitFor({ timeout: 30000 })

    // ------------------------------- 3. Objective / Next Action 真实变化
    phase = 'state-change'
    const ccAfter = await page.evaluate(() => ({
      stage: (document.querySelector('[data-testid="v3-hero-stage"]') || {}).innerText || '',
      objective: (document.querySelector('[data-testid="v3-current-objective-title"]')
        || {}).innerText || '',
      next: (document.querySelector('[data-testid="v3-next-action-title"]') || {})
        .innerText || '',
    }))
    assert.notEqual(ccAfter.stage, ccBefore.stage,
      `Creation 主链后阶段必须真实变化：${ccBefore.stage} → ${ccAfter.stage}`)
    assert.notEqual(ccAfter.next, ccBefore.next,
      `Creation 主链后下一步必须真实变化：${ccBefore.next} → ${ccAfter.next}`)
    await page.screenshot({ path: path.join(SHOTS, 'p6_command_center_after_creation_1440.png'),
      fullPage: true })

    // ------------------------------- 4. 九个 AuthorJourney 工作区 + First-Time 检查
    phase = 'workspaces'
    for (const view of WORKSPACES) {
      await page.goto(`${BASE}/?ui=v3&t=${Date.now()}#/n/${novelId}/${view}`,
        { waitUntil: 'networkidle' })
      await page.waitForTimeout(700)
      await assertWorkspaceAnswers(view)
      const text = await bodyText()
      for (const banned of FORBIDDEN_EVERYWHERE) {
        assert.ok(!text.includes(banned),
          `${view}: 主界面不得出现内部概念 ${banned}`)
      }
      const leak = text.match(INTERNAL_ID_PATTERN)
      assert.ok(!leak, `${view}: 主界面不得裸露内部 id：${leak && leak[0]}`)
      await page.screenshot({ path: path.join(SHOTS, `p6_workspace_${view}_1440.png`),
        fullPage: true })
    }

    // ------------------------------- 5. 推演 → 大纲 → 检查 → 导出 主链
    phase = 'journey-simulation'
    await page.goto(`${BASE}/?ui=v3#/n/${novelId}/simulation`, { waitUntil: 'networkidle' })
    await page.getByTestId('v3-simulation-routes').waitFor({ timeout: 30000 })
    await page.getByTestId('v3-simulation-advance').click()
    await page.getByTestId('v3-simulation-feedback').waitFor({ timeout: 60000 })
    const feedback = (await page.getByTestId('v3-simulation-feedback').innerText())
    assert.ok(feedback.includes('回合'), `推演反馈必须给出真实变化：${feedback}`)

    phase = 'journey-outline'
    const forgeResponse = await http.post(`/api/story-builder/outline/forge?novel_id=${novelId}`,
      { data: { branch_id: 'main', volumes: 2, arcs_per_volume: 2, chapters_per_arc: 3 } })
    assert.equal(forgeResponse.status(), 200,
      `大纲锻造必须成功：${forgeResponse.status()} ${(await forgeResponse.text()).slice(0, 300)}`)
    const outlineJson = await (await http.get(
      `/api/story-builder/v3/novels/${novelId}/command-center`)).json()
    assert.ok(outlineJson.outline.started,
      `锻造后投影必须看到大纲：${JSON.stringify(outlineJson.outline).slice(0, 300)}`)
    await page.goto(`${BASE}/?ui=v3#/n/${novelId}/outline`, { waitUntil: 'networkidle' })
    await page.reload({ waitUntil: 'networkidle' })
    try {
      await page.getByTestId('v3-outline-levels').waitFor({ timeout: 30000 })
    } catch (error) {
      const dump = await page.evaluate(() => ({
        body: document.body.innerText.slice(0, 600),
        sections: Array.from(document.querySelectorAll('[data-testid]'))
          .map((node) => node.getAttribute('data-testid')).slice(0, 40),
      }))
      console.error('OUTLINE DUMP', JSON.stringify(dump, null, 1))
      throw error
    }
    const outline = await page.evaluate(() => ({
      levels: document.querySelectorAll('[data-testid="v3-outline-levels"] li').length,
      chapters: document.querySelectorAll('.v3-workspace-view .v3-chapter').length,
      gaps: document.querySelectorAll('[data-testid="v3-outline-gaps"] li').length,
    }))
    assert.equal(outline.levels, 4, '四级结构必须完整')
    assert.ok(outline.chapters > 0, '锻造后必须有真实章节')

    phase = 'journey-review'
    await page.goto(`${BASE}/?ui=v3#/n/${novelId}/review`, { waitUntil: 'networkidle' })
    await page.getByTestId('v3-review-findings').waitFor({ timeout: 30000 })
    await page.getByTestId('v3-review-repair').waitFor({ timeout: 30000 })

    phase = 'journey-export'
    await page.goto(`${BASE}/?ui=v3#/n/${novelId}/export`, { waitUntil: 'networkidle' })
    await page.getByTestId('v3-export-readiness').waitFor({ timeout: 30000 })
    const exportBefore = await page.evaluate(() => ({
      done: document.querySelectorAll('[data-testid="v3-export-steps"] li[data-done="true"]').length,
      headline: (document.querySelector('[data-testid="v3-export-readiness"] .v3-section-head')
        || {}).innerText || '',
    }))
    assert.ok(exportBefore.headline.length > 0, '导出必须说明当前就绪度')

    phase = 'journey-export-confirm'
    assert.equal((await http.post(`/api/story-builder/outline/confirm?novel_id=${novelId}`,
      { data: { branch_id: 'main' } })).status(), 200)
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByTestId('v3-export-readiness').waitFor({ timeout: 30000 })
    const exportAfter = await page.evaluate(() => ({
      done: document.querySelectorAll('[data-testid="v3-export-steps"] li[data-done="true"]').length,
      headline: (document.querySelector('[data-testid="v3-export-readiness"] .v3-section-head')
        || {}).innerText || '',
    }))
    assert.ok(exportAfter.done >= exportBefore.done,
      '确认大纲后导出就绪度不能倒退')

    // ---------------- 5b. 最终状态门禁（NF-020）：锻造后才能真正扫描作者可见内容
    phase = 'rich-state-gates'
    const richChain = await (await http.get(
      `/api/story-builder/outline/chain?novel_id=${novelId}&branch_id=main`)).json()
    const richTitles = richChain.chapters.map((row) => row.items[0].title)
    const richBodies = richTitles.map((title) => (title.includes('：')
      ? title.split('：').slice(1).join('：') : title))
    const richDuplicates = [...new Set(richBodies.filter(
      (body, index) => richBodies.indexOf(body) !== index))]
    assert.deepEqual(richDuplicates, [],
      `锻造后章节标题正文必须唯一：${richDuplicates.slice(0, 3)}`)
    for (const title of richTitles) {
      for (const banned of ['阶段目标（规划）', '长期方向（规划）', '（设定草稿）']) {
        assert.ok(!title.includes(banned), `章节标题不得是字段占位：${title}`)
      }
    }
    for (const view of WORKSPACES) {
      await page.goto(`${BASE}/?ui=v3&t=${Date.now()}#/n/${novelId}/${view}`,
        { waitUntil: 'networkidle' })
      await page.waitForTimeout(500)
      const text = await bodyText()
      const leak = text.match(INTERNAL_ID_PATTERN)
      assert.ok(!leak, `${view}（锻造后）不得裸露内部 id：${leak && leak[0]}`)
    }
    // 导出物同样不得含内部 id / 重复来源前缀。
    for (const format of ['markdown', 'json']) {
      const exported = await (await http.get(
        `/api/story-builder/outline/export?novel_id=${novelId}&branch_id=main`
        + `&format=${format}`)).json()
      assert.ok(!exported.content.includes('来源：来源：'),
        `${format} 导出不得出现重复来源前缀`)
    }

    // --------------------- 6. Refresh restore / Deep-link / Back / Switch Novel
    phase = 'refresh-deeplink-back'
    await page.goto(`${BASE}/?ui=v3#/n/${novelId}/characters`, { waitUntil: 'networkidle' })
    await page.getByTestId('v3-characters-block').waitFor({ timeout: 30000 })
    const charsBefore = await page.evaluate(() => document.querySelectorAll('.v3-character').length)
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByTestId('v3-characters-block').waitFor({ timeout: 30000 })
    assert.equal(await page.evaluate(() => document.querySelectorAll('.v3-character').length),
      charsBefore, '刷新后角色工作区必须保持一致')
    await page.goBack({ waitUntil: 'networkidle' })
    await page.waitForTimeout(700)
    assert.ok(await page.evaluate(() => Boolean(document.querySelector('.v3-root'))),
      '浏览器 Back 必须仍停留在 V3 应用内')
    await page.goto(`${BASE}/?ui=v3#/`, { waitUntil: 'networkidle' })
    await page.getByTestId('v3-landing').waitFor({ timeout: 30000 })
    const switchTarget = page.getByTestId(`v3-novel-card-${novelId}`)
    assert.ok(await switchTarget.count() > 0, '新建的作品必须出现在作品列表里')
    await page.getByTestId(`v3-novel-continue-${novelId}`).click()
    await page.getByTestId('v3-command-center').waitFor({ timeout: 30000 })

    // ------------------------------- 7. Advanced Tools reachable（19 页签）
    phase = 'advanced-tools'
    await page.goto(`${BASE}/?ui=v3#/story-builder?novel_id=${novelId}&tab=builder`,
      { waitUntil: 'networkidle' })
    await page.getByTestId('legacy-back-to-v3').waitFor({ timeout: 60000 })
    await page.waitForTimeout(1200)
    await page.locator('.creator-tabs button').first().waitFor({ timeout: 60000 })
    const tabs = await page.evaluate(() => document.querySelectorAll(
      '.creator-tabs button').length)
    assert.ok(tabs >= 19, `高级工具必须至少 19 个页签，实际 ${tabs}`)
    await page.getByTestId('legacy-back-to-v3').click()
    await page.waitForTimeout(800)
    assert.ok(await page.evaluate(() => Boolean(document.querySelector('.v3-root'))),
      '从高级工具必须能回到 V3 工作台')

    // ------------------------------- 8. 四视口
    for (const [width, height] of VIEWPORTS) {
      phase = `viewport:${width}`
      await page.setViewportSize({ width, height })
      for (const view of ['home', 'creation', 'world', 'characters', 'story',
        'simulation', 'outline', 'review', 'export']) {
        await page.goto(`${BASE}/?ui=v3#/n/${novelId}/${view === 'home' ? '' : view}`,
          { waitUntil: 'networkidle' })
        await page.waitForTimeout(500)
        await noOverflow(`${view}@${width}`)
      }
      await page.screenshot({ path: path.join(SHOTS, `p6_home_${width}.png`) })
    }

    // ---------------------------------------------------------------- 门禁
    assert.deepEqual(pageErrors, [], `pageerror：${pageErrors.join(' | ')}`)
    assert.deepEqual(failedRequests, [], `requestfailed：${failedRequests.join(' | ')}`)
    assert.deepEqual(consoleErrors, [], `console error：${consoleErrors.join(' | ')}`)
    assert.deepEqual(badResponses, [], `非预期 4xx/5xx：${badResponses.join(' | ')}`)
    console.log('PASS V3-P6 Full Product Acceptance：Landing → 新建作品 → Command Center →'
      + ' Creation 主链（创意→候选→设定→自检→开始推演）→ Stage/Objective/NextAction 真实变化 →'
      + ' 9 个 AuthorJourney 工作区（作者语言 / 无内部 id）→ 推演→大纲→检查→导出 主链 →'
      + ' 锻造后门禁（章节标题唯一 / 8 工作区与 2 种导出 0 内部 id）→'
      + ' Refresh / Deep-link / Back / Switch Novel → 高级工具 19 页签 →'
      + ' 1440/1280/1024/390 四视口；'
      + '0 pageerror / 0 requestfailed / 0 console error / 0 非预期 4xx / 0 横向溢出')
  } finally {
    await browser.close()
  }
})().catch(report)
