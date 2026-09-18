// NovelForge Product V3 — UI Foundation 实机验收（Edge / Playwright）。
//
// 覆盖：
//   启动 → 选择作品 → Command Center → 一句话创意 → 候选 → 选择设定 → 设定自检
//   → 开始推演 → Next Action / Objective 更新 → 刷新恢复 → 深链接恢复
//   → 1440 / 1280 / 1024 / 390 视觉检查 + 截图
//
// 运行前提（隔离数据，不接触作者数据）：
//   .venv\Scripts\python.exe scripts/creator_ui_test_server.py --port 8030 --root workspace/v3_ui_test_root
//   node tests/browser_v3_ui_foundation.cjs   （Playwright 自行安装：npm i -D playwright）
const { chromium, request } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const BASE = process.env.V3_BASE || 'http://127.0.0.1:8030'
const SHOTS = process.env.V3_SHOTS || 'workspace/product_v3/visual_review'
const IDEA = '一个修伞匠发现城市每天都在重写同一场雨。'

const VIEWPORTS = [
  { name: '1440', width: 1440, height: 1000 },
  { name: '1280', width: 1280, height: 900 },
  { name: '1024', width: 1024, height: 900 },
  { name: '390', width: 390, height: 844 },
]

async function noHorizontalOverflow(page, label) {
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  assert.ok(overflow.scrollWidth <= overflow.clientWidth + 1,
    `${label}: 出现横向溢出 ${overflow.scrollWidth} > ${overflow.clientWidth}`)
}

;(async () => {
  fs.mkdirSync(SHOTS, { recursive: true })
  const pageErrors = []
  const consoleErrors = []
  const badResponses = []
  const http = await request.newContext({ baseURL: BASE })
  const novelId = process.env.V3_NOVEL || ('novel_v3_accept_' + (Date.now() % 1000000))
  const browser = await chromium.launch({ channel: 'msedge', headless: true })

  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    page.on('pageerror', (error) => pageErrors.push(String(error)))
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })
    page.on('response', (response) => {
      if (response.status() >= 400) {
        badResponses.push(`${response.status()} ${response.url()}`)
      }
    })

    // ---------------------------------------------------------- 1 启动 / Landing
    await page.goto(`${BASE}/?ui=v3`, { waitUntil: 'networkidle' })
    await page.getByTestId('v3-landing').waitFor({ timeout: 20000 })
    await page.getByTestId('v3-landing-new').waitFor()
    await page.screenshot({ path: path.join(SHOTS, 'v3_01_landing_1440.png') })

    // ---------------------------------------------------------- 2 新建作品
    await page.getByTestId('v3-landing-new').click()
    await page.getByLabel('新作品编号').fill(novelId)
    await page.getByTestId('v3-landing-create-submit').click()

    // ------------------------------------------------- 3 Command Center 首屏
    await page.getByTestId('v3-command-center').waitFor({ timeout: 30000 })
    await page.getByTestId('v3-novel-hero').waitFor()
    assert.ok((await page.getByTestId('v3-hero-title').innerText()).length > 0)
    const heroStage = await page.getByTestId('v3-hero-stage').innerText()
    assert.ok(heroStage.includes('当前阶段'), '首屏必须直接说明当前阶段')
    assert.ok(heroStage.includes('创意'), '新作品必须停在创意阶段')
    await page.getByTestId('v3-stage-track').waitFor()
    for (const stage of ['creation', 'world', 'characters', 'story', 'simulation',
      'outline', 'review', 'export']) {
      await page.getByTestId(`v3-stage-${stage}`).waitFor()
    }
    assert.ok((await page.getByTestId('v3-current-objective-title').innerText()).length > 0,
      'Command Center 必须直接显示当前目标')
    assert.ok((await page.getByTestId('v3-next-action-title').innerText()).length > 0,
      'Command Center 必须直接显示下一步')
    assert.ok((await page.getByTestId('v3-next-action-cta').innerText()).length > 0,
      '下一步必须带动作型 CTA')
    // 开发者语言不得泄漏到主界面。
    const body = await page.locator('body').innerText()
    for (const leak of ['StoryState', 'planning', 'Canon', 'API', 'truth_layer',
      'objective_id', 'revision']) {
      assert.ok(!body.includes(leak), `主界面出现开发者术语：${leak}`)
    }
    await page.screenshot({ path: path.join(SHOTS, 'v3_02_command_center_1440.png') })

    // ------------------------------------------- 4 第一条真实流程：一句话创意
    await page.getByTestId('v3-next-action-cta').click()
    await page.getByTestId('v3-creation-workspace').waitFor({ timeout: 20000 })
    await page.getByTestId('v3-creation-goal-title').waitFor()
    await page.screenshot({ path: path.join(SHOTS, 'v3_03_creation_1440.png') })

    await page.getByLabel('一句话创意').fill(IDEA)
    await page.getByLabel('读者体验').fill('悬疑、温柔')
    await page.getByTestId('v3-idea-suggest').click()
    await page.getByTestId('v3-genre-candidates').waitFor({ timeout: 30000 })
    await page.getByTestId('v3-genre-candidates-card').first().click()
    await page.screenshot({ path: path.join(SHOTS, 'v3_04_idea_candidates_1440.png') })
    await page.getByTestId('v3-idea-save').click()
    await page.waitForFunction(() => document
      .querySelector('[data-testid="v3-flow-step-idea"]')
      ?.className.includes('is-done'), null, { timeout: 30000 })

    // 游戏式反馈必须说明进度变化 / 解锁 / 下一步。
    const feedback = await page.getByTestId('v3-feedback').innerText()
    assert.ok(feedback.includes('已解锁'), '反馈必须说明解锁了什么')
    assert.ok(feedback.includes('下一步'), '反馈必须说明下一步')
    assert.ok(/→/.test(feedback), '反馈必须说明进度变化')

    // ------------------------------------------------ 5 设定候选 → 保存 → 自检
    await page.getByTestId('v3-flow-step-settings').click()
    await page.getByTestId('v3-settings-suggest').click()
    await page.getByTestId('v3-setting-groups').waitFor({ timeout: 40000 })
    const groups = await page.getByTestId('v3-setting-groups').locator('details').count()
    assert.ok(groups >= 5, `设定分组过少：${groups}`)
    await page.locator('[data-testid="v3-setting-group-world_rules"] summary').click()
    await page.locator('[data-testid="v3-setting-candidate-world_rules"]').first().click()
    await page.screenshot({ path: path.join(SHOTS, 'v3_05_settings_1440.png') })
    await page.getByTestId('v3-settings-save').click()
    await page.waitForFunction(() => document
      .querySelector('[data-testid="v3-flow-step-settings"]')
      ?.className.includes('is-done'), null, { timeout: 60000 })

    // ------------------------------------------------------------- 6 自检
    await page.getByTestId('v3-flow-step-check').click()
    await page.getByTestId('v3-check-run').click()
    await page.getByTestId('v3-check-result').waitFor({ timeout: 60000 })
    await page.screenshot({ path: path.join(SHOTS, 'v3_06_setting_check_1440.png') })
    const checkText = await page.getByTestId('v3-check-result').innerText()
    assert.ok(checkText.length > 0)
    // 若还有缺项，允许修补一次（真实引擎行为，不是测试绕过）。
    if (!checkText.includes('自检通过')) {
      await page.getByTestId('v3-check-repair').click()
      await page.waitForFunction(() => document
        .querySelector('[data-testid="v3-flow-step-check"]')
        ?.className.includes('is-done'), null, { timeout: 60000 })
    }

    // ------------------------------------------------------------- 7 开始推演
    const beforeRuntime = await (await http.get(
      `/api/story-builder/v3/novels/${novelId}/command-center`)).json()
    assert.equal(beforeRuntime.facts.runtime_started, false)
    await page.getByTestId('v3-flow-step-runtime').click()
    await page.getByTestId('v3-runtime-ready').waitFor({ timeout: 20000 })
    await page.getByTestId('v3-runtime-start').click()
    await page.waitForFunction(() => document
      .querySelector('[data-testid="v3-flow-step-runtime"]')
      ?.className.includes('is-done'), null, { timeout: 90000 })
    await page.screenshot({ path: path.join(SHOTS, 'v3_07_runtime_started_1440.png') })

    // ------------------------------------------- 8 Objective / Next Action 更新
    const afterRuntime = await (await http.get(
      `/api/story-builder/v3/novels/${novelId}/command-center`)).json()
    assert.equal(afterRuntime.facts.runtime_started, true)
    // 真实状态必须前进：整体进度变高，或者阶段推进（推演完成后进入产出侧）。
    assert.ok(
      afterRuntime.progress.percent > beforeRuntime.progress.percent
      || afterRuntime.progress.done > beforeRuntime.progress.done
      || afterRuntime.journey.current_stage !== beforeRuntime.journey.current_stage,
      '真实进度必须随推演开始而前进')
    assert.notEqual(afterRuntime.next_action.title, beforeRuntime.next_action.title,
      'Next Action 必须随状态变化更新')
    assert.ok(['outline', 'review', 'export'].includes(afterRuntime.journey.current_stage),
      `推演后阶段应进入产出侧，实际 ${afterRuntime.journey.current_stage}`)

    // ------------------------------------------------------- 9 刷新恢复
    await page.goto(`${BASE}/?ui=v3#/n/${novelId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('v3-command-center').waitFor({ timeout: 30000 })
    const restoredStage = await page.getByTestId('v3-hero-stage').innerText()
    assert.ok(restoredStage.includes(afterRuntime.journey.current_stage_label),
      '刷新后必须恢复到同一阶段')
    assert.equal(await page.getByTestId('v3-next-action-title').innerText(),
      afterRuntime.next_action.title)

    // ------------------------------------------------------- 10 深链接恢复
    await page.goto(`${BASE}/?ui=v3#/n/${novelId}/creation?step=check`, { waitUntil: 'networkidle' })
    await page.getByTestId('v3-flow-check').waitFor({ timeout: 30000 })
    assert.ok(await page.getByTestId('v3-flow-step-check').getAttribute('class')
      .then((value) => value.includes('is-active')), '深链接必须直接打开对应步骤')

    // ------------------------------------------------- 11 Next Action 深度链接
    await page.goto(`${BASE}/?ui=v3#/n/${novelId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('v3-command-center').waitFor({ timeout: 30000 })
    await page.getByTestId('v3-next-action-cta').click()
    await page.waitForFunction((expected) => {
      const active = document.querySelector('.v3-nav-item.is-active .v3-nav-label')
      return Boolean(active && active.textContent && active.textContent.length > 0)
    }, null, { timeout: 20000 })
    const activeNav = await page.locator('.v3-nav-item.is-active .v3-nav-label').innerText()
    assert.ok(activeNav.length > 0, 'Next Action 必须把作者带到对应工作区')

    // ------------------------------------------------------- 12 Objective 面板
    await page.goto(`${BASE}/?ui=v3#/n/${novelId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('v3-command-center').waitFor({ timeout: 30000 })
    await page.getByTestId('v3-current-objective-cta').click()
    await page.getByTestId('v3-context-panel').waitFor({ timeout: 20000 })
    assert.ok((await page.getByTestId('v3-context-panel').innerText()).includes('为什么重要'))
    await page.getByTestId('v3-context-close').click()

    // ------------------------------------------------- 13 一级导航不含高级工具
    const navText = await page.locator('.v3-nav-list').innerText()
    for (const forbidden of ['Inspector', 'Canon', 'Repair', 'Truth', 'Provenance', 'Debug']) {
      assert.ok(!navText.includes(forbidden), `一级导航泄漏高级工具：${forbidden}`)
    }
    // 高级工具仍然可达（同一个应用内的 legacy 面板）。
    await page.getByTestId('v3-nav-legacy').click()
    await page.getByTestId('legacy-back-to-v3').waitFor({ timeout: 20000 })
    await page.goto(`${BASE}/?ui=v3#/n/${novelId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('v3-command-center').waitFor({ timeout: 20000 })

    // ------------------------------------------------------- 14 视觉 / 响应式
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.waitForTimeout(400)
      await noHorizontalOverflow(page, `${viewport.name}px`)
      await page.screenshot({
        path: path.join(SHOTS, `v3_08_command_center_${viewport.name}.png`),
      })
      await page.getByTestId('v3-workspace').waitFor({ timeout: 10000 })
      await page.getByTestId('v3-topbar-stage').waitFor({ timeout: 10000 })
      if (viewport.width > 1024) {
        // 宽屏：右侧栏常驻，Next Action 必须一直可见。
        await page.getByTestId('v3-next-action-cta').waitFor({ timeout: 10000 })
      } else {
        // 窄屏：右侧栏折叠为抽屉，但入口必须存在且可打开。
        await page.getByTestId('v3-rail-toggle').waitFor({ timeout: 10000 })
      }
    }

    // 390px：Next Action 必须可见且可操作（右栏折叠为抽屉）。
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByTestId('v3-rail-toggle').click()
    await page.waitForTimeout(300)
    await page.getByTestId('v3-next-action-cta').waitFor({ timeout: 10000 })
    assert.ok(await page.getByTestId('v3-next-action-cta').isVisible(),
      '390px 下 Next Action CTA 必须可见可点')
    await page.screenshot({ path: path.join(SHOTS, 'v3_09_mobile_rail_390.png') })
    // Esc 必须能关闭抽屉（无障碍要求），关闭后抽屉不再占据屏幕。
    await page.keyboard.press('Escape')
    await page.waitForTimeout(200)
    assert.ok(!(await page.getByTestId('v3-rail').isVisible()),
      'Esc 必须收起移动端目标抽屉')

    // ---------------------------------------- 15 首次使用者可理解性（≤5 秒）
    const firstScreen = await page.evaluate(() => {
      const pick = (selector) => document.querySelector(selector)?.textContent?.trim() ?? ''
      return {
        stage: pick('[data-testid="v3-topbar-stage"]'),
        objective: pick('[data-testid="v3-current-objective-title"]'),
        action: pick('[data-testid="v3-next-action-cta"]'),
        reason: pick('[data-testid="v3-next-action-reason"]'),
      }
    })
    assert.ok(firstScreen.stage.length > 0, '首屏必须说明当前阶段')
    assert.ok(firstScreen.objective.length > 0, '首屏必须说明当前目标')
    assert.ok(firstScreen.action.length > 0, '首屏必须给出主要操作')
    assert.ok(firstScreen.reason.length > 0, '首屏必须说明为什么做')

    // V3 页面不允许出现任何未捕获异常 / 失败请求。
    // 唯一允许的 404 是 V2 legacy 面板“还没有会话”时的既有探测（同样被 V2 面板捕获）。
    assert.deepEqual(pageErrors, [], `出现未捕获异常：${pageErrors.join(' | ')}`)
    const unexpected = badResponses.filter((row) => !row.includes('/api/story-builder/sessions/latest'))
    assert.deepEqual(unexpected, [], `出现失败请求：${unexpected.join(' | ')}`)
    const unexpectedConsole = consoleErrors.filter((row) => !row.includes('404'))
    assert.deepEqual(unexpectedConsole, [], `控制台出现错误：${unexpectedConsole.join(' | ')}`)
    console.log('V3 UI FOUNDATION browser acceptance: PASS')
    console.log('novel_id:', novelId)
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
