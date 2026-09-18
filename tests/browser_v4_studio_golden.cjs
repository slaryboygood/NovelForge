/*
 * NovelForge V4-10 Story Studio 浏览器门禁（真实浏览器 + stub 模型，零网络）。
 *
 * 覆盖（任务书 §83–§88、§104）：
 *   A 生成流程：新建作品 → Overview → 逐级生成（premise/world/character/story_arc/
 *     structural_unit/chapter/scene）→ 卡片出现 → 打开场景抽屉 → 字段编辑 → 保存新版本
 *     → 看到 Diff → 接受
 *   B 冲突流程：打开 r1 → 后台 hook 生成 r2 → 保存 → 409 → 冲突面板（我的/当前/差异）
 *   C 质量流程：检查中心 → gate 面板 → issue 卡片（人类文案 + 诊断码）→ repair 预览
 *   D 交付下载：干净作品 → 交付 → manifest → 真实下载 Markdown / DOCX / nfpack
 *   E 插件页：trust model（trusted in-process，非沙箱）+ 只读列表
 *   F 响应式：1440 / 1280 / 1024 / 390 无横向溢出 + 0 pageerror
 *
 * 运行：
 *   .venv\\Scripts\\python.exe scripts/studio_ui_test_server.py --port 8040 --root workspace/studio_ui_test_root
 *   node tests/browser_v4_studio_golden.cjs
 */
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const BASE = process.env.STUDIO_BASE || 'http://127.0.0.1:8040'
const SHOTS = process.env.STUDIO_SHOTS || 'workspace/studio_ui_review'
const NOVEL = process.env.STUDIO_NOVEL || 'studio_demo'
const CLEAN = process.env.STUDIO_CLEAN || 'studio_clean'
const DOWNLOADS = path.resolve(SHOTS, 'downloads')
const VIEWPORTS = [[1440, 1000], [1280, 900], [1024, 900], [390, 844]]

const errors = []
const badResponses = []

function track(page, phase) {
  page.on('pageerror', (error) => errors.push(`${phase}: ${error.message}`))
  page.on('console', (message) => {
    if (message.type() !== 'error') return
    const text = message.text()
    // 409（revision conflict）与 422（校验/缺模型）是**被覆盖的预期路径**
    if (/409 \(Conflict\)/.test(text) || /422 \(/.test(text)) return
    errors.push(`${phase}: console ${text}`)
  })
  page.on('response', (response) => {
    const status = response.status()
    if (status >= 400 && ![409, 422].includes(status)) {
      badResponses.push(`${phase}: ${status} ${response.url().replace(BASE, '')}`)
    }
  })
}

async function open(page, hash, phase) {
  track(page, phase)
  await page.goto(`${BASE}/?t=${Date.now()}${hash}`, { waitUntil: 'networkidle' })
}

async function shot(page, name) {
  fs.mkdirSync(SHOTS, { recursive: true })
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true })
}

async function step(label, action) {
  console.log(`[step] ${label}`)
  await action()
}

/** 关闭当前通知（避免覆盖抽屉按钮；产品 6 秒会自动消失）。 */
async function clearToasts(page) {
  const closers = page.locator('[data-testid="studio-toasts"] button')
  const count = await closers.count()
  for (let index = 0; index < count; index += 1) {
    await closers.nth(index).click({ timeout: 2000 }).catch(() => {})
  }
}

async function noOverflow(page, label) {
  const overflow = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }))
  assert.ok(overflow.scroll <= overflow.client + 2,
    `${label} 横向溢出：${overflow.scroll} > ${overflow.client}`)
}

;(async () => {
  fs.mkdirSync(DOWNLOADS, { recursive: true })
  const browser = await chromium.launch({ channel: 'msedge' })
  const context = await browser.newContext({ acceptDownloads: true,
    viewport: { width: 1440, height: 1000 } })
  const page = await context.newPage()

  /* ---------------------------------------------------------------- A 生成 */
  await open(page, '#/studio', 'landing')
  await page.waitForSelector('[data-testid="studio-landing"]')
  await shot(page, '01-landing')

  await page.fill('[data-testid="novel-id"]', NOVEL)
  await page.fill('[data-testid="novel-title"]', '断电边城')
  await page.click('[data-testid="create-novel"]')
  await page.waitForSelector('[data-testid="studio-overview"]', { timeout: 15000 })
  await page.waitForSelector('[data-testid="topbar-title"]')
  await shot(page, '02-overview-empty')

  // 逐级生成：每步都是 proposal（待接受），不是自动接受
  /** 父节点选择面板：多候选时出现（§3.6）。返回提示文案，便于断言。 */
  const resolveParentPrompt = async (expectText = '') => {
    const prompt = page.locator('[data-testid="parent-prompt"]')
    await prompt.waitFor({ state: 'visible', timeout: 15000 })
    const text = await prompt.textContent()
    if (expectText) {
      assert.ok(text.includes(expectText), `父节点提示文案不符：${text}`)
    }
    await clearToasts(page)
    await page.locator('[data-testid^="parent-option-"]').first().click()
    await clearToasts(page)
    await page.click('[data-testid="parent-confirm"]')
    await page.waitForSelector('[data-testid="parent-prompt"]',
      { state: 'detached', timeout: 15000 })
    return text
  }

  const generate = async (testId) => {
    console.log(`[step] generate ${testId}`)
    await page.waitForSelector(`[data-testid="${testId}"]`, { timeout: 15000 })
    await page.click(`[data-testid="${testId}"]`)
    // 确定性等待「两种可能信号」之一：父节点选择面板（多候选）或长操作面板。
    const signal = await Promise.race([
      page.waitForSelector('[data-testid="parent-prompt"]', { state: 'visible',
        timeout: 8000 }).then(() => 'prompt').catch(() => 'waiting'),
      page.waitForSelector('[data-testid="studio-operation"]', { state: 'visible',
        timeout: 8000 }).then(() => 'operation').catch(() => 'waiting'),
    ])
    if (signal === 'prompt') {
      await resolveParentPrompt()
    }
    await page.waitForSelector('[data-testid="studio-operation"]',
      { state: 'detached', timeout: 30000 }).catch(() => {})
    // 失败必须立刻暴露（不要静默跳过生成步骤）
    const failure = page.locator('[data-testid="toast-error"]')
    if (await failure.count() > 0) {
      throw new Error(`生成失败（${testId}）：${await failure.first().textContent()}`)
    }
  }

  await page.click('[data-testid="nav-creation"]')
  await generate('generate-premise')
  await page.click('[data-testid="nav-world"]')
  await generate('generate-world')
  await page.click('[data-testid="nav-characters"]')
  await generate('generate-character')
  await page.click('[data-testid="nav-story"]')
  await generate('generate-story_arc')
  await generate('generate-structural_unit')
  await generate('generate-chapter')

  // §5：再建一个 chapter（走 REST，等价于作者的第二次创建），随后验证
  // 「多个 chapter + 未显式指定父节点 → UI 不猜，要求作者选择」。
  const chapterId = await page.evaluate(async (novelId) => {
    const blueprint = await (await fetch(
      `/api/story-builder/studio/blueprint?novel_id=${novelId}`)).json()
    const chapter = blueprint.nodes.find((row) => row.node_type === 'chapter')
    await fetch('/api/story-builder/studio/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ novel_id: novelId, task: 'chapter',
        parent_id: chapter ? chapter.parent_id || '' : '', index: 2 }),
    })
    const after = await (await fetch(
      `/api/story-builder/studio/blueprint?novel_id=${novelId}`)).json()
    return after.nodes.filter((row) => row.node_type === 'chapter').length
  }, NOVEL)
  assert.ok(chapterId >= 2, `第二次 chapter 未创建（chapter=${chapterId}）`)

  // §1/§5 回归：chapter 就绪后**立即**生成 scene（不刷新页面、不等待 React 重渲染），
  // 且多 chapter 时不得 latest-wins —— 必须出现父节点选择面板。
  await page.click('[data-testid="nav-scenes"]')
  await page.click('[data-testid="generate-scene"]')
  await resolveParentPrompt('选择上级内容')
  await page.waitForSelector('[data-testid^="node-card-"]', { timeout: 20000 })
  await shot(page, '03-scenes')
  await page.waitForSelector('[data-testid="studio-operation"]',
    { state: 'detached', timeout: 30000 }).catch(() => {})
  await shot(page, '03b-parent-prompt')

  // 场景卡片正面必须回答「这场戏为什么存在」
  const functionText = await page.textContent('[data-testid="scene-function"]')
  assert.ok(functionText && functionText.includes('这场戏的作用'),
    'Scene Card 未突出故事功能')

  /* -------------------------------------------------------------- 编辑流程 */
  const sceneCard = page.locator('[data-testid^="node-card-"]').first()
  await sceneCard.click()
  await page.waitForSelector('[data-testid="node-drawer"]')
  await page.waitForSelector('[data-testid="node-status"]')
  await shot(page, '04-drawer')

  const outcome = page.locator('.studio-field').filter({ hasText: '结果' })
    .locator('textarea, input').first()
  const before = await outcome.inputValue()
  await outcome.fill(`${before}（作者补写：留下一个未解释的细节）`)
  await page.click('[data-testid="save-node"]')
  await page.waitForSelector('[data-testid="toast-success"]', { timeout: 20000 })
  await page.waitForSelector('[data-testid="diff-view"]', { timeout: 15000 })
  await shot(page, '05-save-diff')

  // 接受（作者决定；与质量通过无关）
  await page.click('[data-testid="accept-node"]')
  await page.waitForSelector('[data-testid="toast-success"]', { timeout: 20000 })
  // 接受后抽屉会重新读取节点（异步）：轮询直到状态徽章变为「已接受」
  await page.waitForFunction(
    () => (document.querySelector('[data-testid="node-status"]')?.textContent || '')
      .includes('已接受'), null, { timeout: 20000 })
  const statusText = await page.textContent('[data-testid="node-status"]')
  assert.ok(statusText.includes('已接受'), `节点未变为 accepted：${statusText}`)

  /* -------------------------------------------------------------- B 冲突 */
  const revision = await page.evaluate(async (novelId) => {
    const url = `/api/story-builder/studio/blueprint?novel_id=${novelId}`
    const data = await (await fetch(url)).json()
    const scene = data.nodes.find((row) => row.node_type === 'scene')
    return scene ? { id: scene.node_id, revision: scene.revision } : null
  }, NOVEL)
  assert.ok(revision, '找不到场景节点')

  // 后台 hook：直接改同一个人节点（产生新 revision），页面仍停在自己的版本
  await page.evaluate(async ({ novelId, nodeId }) => {
    await fetch(`/api/story-builder/editor/nodes/${nodeId}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ novel_id: novelId,
        changes: { conflict: '后台改写：许可被彻底取消' },
        reason: 'background hook' }),
    })
  }, { novelId: NOVEL, nodeId: revision.id })

  await outcome.fill(`${before}（作者本地版本）`)
  await page.click('[data-testid="save-node"]')
  await page.waitForSelector('[data-testid="conflict-panel"]', { timeout: 20000 })
  const conflictText = await page.textContent('[data-testid="conflict-panel"]')
  assert.ok(conflictText.includes('内容已被更新'), '冲突面板文案不正确')
  assert.ok(await page.locator('[data-testid="conflict-reload"]').isVisible(),
    '冲突面板缺少「查看最新版本」动作')
  await shot(page, '06-conflict')
  await page.click('[data-testid="drawer-close"]')

  /* -------------------------------------------------------------- C 质量 */
  await page.click('[data-testid="nav-quality"]')
  await page.waitForSelector('[data-testid="workspace-quality"]')
  await page.click('[data-testid="quality-evaluate"]')
  await page.waitForSelector('[data-testid="gate-Q0"]', { timeout: 30000 })
  await page.waitForTimeout(500)
  await shot(page, '07-quality')

  const gateCount = await page.locator('[data-testid^="gate-Q"]').count()
  assert.ok(gateCount >= 10, `门禁面板不完整：${gateCount}`)

  const issueCard = page.locator('[data-testid^="issue-"]').first()
  if (await issueCard.count() > 0) {
    await issueCard.click()
    await page.waitForSelector('[data-testid="issue-drawer"]')
    const detail = await page.textContent('[data-testid="issue-drawer"]')
    assert.ok(detail.includes('诊断'), 'issue 详情缺少诊断信息')
    await shot(page, '08-issue-detail')
    await page.click('[data-testid="drawer-close"]')
  }

  // 修复预览：必须有「改哪里 / 允许改什么 / 保留什么 / 复核哪些 gate」
  const selectAll = page.locator('[data-testid="quality-select-all"]')
  if (await selectAll.count() > 0) {
    await selectAll.click()
    await page.click('[data-testid="quality-plan-repair"]')
    await page.waitForSelector('[data-testid="repair-preview"]', { timeout: 30000 })
    const preview = await page.textContent('[data-testid="repair-preview"]')
    assert.ok(preview.includes('将修改节点') || preview.includes('没有可修复'),
      '修复预览缺少改动范围说明')
    await shot(page, '09-repair-preview')
    await page.click('[data-testid="drawer-close"]')
  }

  /* -------------------------------------------------------------- D 交付 */
  await open(page, `#/studio/n/${CLEAN}/delivery`, 'delivery')
  await page.waitForSelector('[data-testid="workspace-delivery"]', { timeout: 15000 })
  await page.waitForSelector('[data-testid="format-markdown"]')
  const formatIds = await page.locator('[data-testid^="format-"]').count()
  assert.ok(formatIds >= 4, `交付格式列表不完整：${formatIds}`)
  assert.ok(await page.locator('[data-testid="format-tlist"]').count() > 0,
    '插件 exporter 的格式没有出现在交付列表（§55）')
  // 默认已勾选 json + markdown：只补选缺失的格式（不误取消）
  for (const format of ['markdown', 'docx', 'nfpack']) {
    const chip = page.locator(`[data-testid="format-${format}"]`)
    if (await chip.getAttribute('aria-pressed') !== 'true') await chip.click()
  }
  await page.click('[data-testid="deliver-submit"]')
  await page.waitForSelector('[data-testid="delivery-result"]', { timeout: 60000 })
  const deliveryStatus = await page.textContent('[data-testid="delivery-status"]')
  assert.ok(deliveryStatus.includes('已交付'), `交付未完成：${deliveryStatus}`)
  await shot(page, '10-delivery')

  for (const format of ['markdown', 'docx', 'nfpack']) {
    const link = page.locator(`[data-testid="download-${format}"]`)
    assert.ok(await link.count() > 0, `缺少 ${format} 下载入口`)
    const [download] = await Promise.all([page.waitForEvent('download'), link.click()])
    const target = path.join(DOWNLOADS, download.suggestedFilename())
    await download.saveAs(target)
    const size = fs.statSync(target).size
    assert.ok(size > 0, `${format} 下载为空文件`)
    assert.ok(download.suggestedFilename().length > 0, `${format} 下载文件名缺失`)
    console.log(`[download] ${format}: ${download.suggestedFilename()} (${size} bytes)`)
  }

  /* ------------------------------------------------------------- E 插件 */
  await page.click('[data-testid="nav-plugins"]')
  await page.waitForSelector('[data-testid="workspace-plugins"]', { timeout: 15000 })
  const trust = await page.textContent('[data-testid="plugin-trust-model"]')
  assert.ok(trust.includes('Trusted in-process'), '插件页未显示 trust model')
  assert.ok(!trust.includes('沙箱隔离'), '插件页出现了虚假的沙箱承诺')
  assert.ok(await page.locator('[data-testid^="plugin-com.example"]').count() > 0,
    '插件列表为空')
  await shot(page, '11-plugins')

  /* ---------------------------------------------------------- F 响应式 */
  for (const [width, height] of VIEWPORTS) {
    await page.setViewportSize({ width, height })
    await open(page, `#/studio/n/${CLEAN}`, `viewport-${width}`)
    await page.waitForSelector('[data-testid="studio-overview"]', { timeout: 15000 })
    await noOverflow(page, `overview@${width}`)
    await shot(page, `12-overview-${width}`)
  }

  await browser.close()

  assert.deepEqual(errors, [], `页面出现错误：\n${errors.join('\n')}`)
  assert.deepEqual(badResponses, [], `出现非预期响应：\n${badResponses.join('\n')}`)
  console.log('V4-10 Story Studio browser gate: PASS')
})().catch((error) => {
  console.error('V4-10 Story Studio browser gate: FAIL')
  console.error(error)
  process.exit(1)
})
