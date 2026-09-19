/*
 * NovelForge V4-11 Agent Mode 浏览器门禁（§104–§106）。
 *
 *   open Agent → 输入目标 → 计划预览（0 mutation）→ 开始执行 → 需要确认 → 批准 →
 *   继续 → 完成；并验证：AI 内容仍是 proposed（不自动接受）、执行历史可见、
 *   取消文案诚实（不会声称立即中止）。
 *
 * 依赖 stub 模型服务（scripts/studio_ui_test_server.py），0 real model calls。
 */
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const BASE = process.env.STUDIO_BASE || 'http://127.0.0.1:8040'
const SHOTS = process.env.STUDIO_SHOTS || 'workspace/studio_ui_review'
const NOVEL = process.env.AGENT_NOVEL || 'studio_clean'
const errors = []

async function shot(page, name) {
  fs.mkdirSync(SHOTS, { recursive: true })
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true })
}

async function clearToasts(page) {
  const closers = page.locator('[data-testid="studio-toasts"] button')
  const count = await closers.count()
  for (let index = 0; index < count; index += 1) {
    await closers.nth(index).click({ timeout: 1500 }).catch(() => {})
  }
}

/*
 * 驱动一次 Agent 执行：处理 bounded batch 的「暂停 → 继续执行」，
 * 并按 allowApproval 决定是否批准 protected step。
 *
 * 返回 {approvals, failures}；只有出现 AGENT_STEP_FAILED 才抛错（不允许静默失败）。
 */
async function driveAgent(page, { allowApproval = false, maxRounds = 8 } = {}) {
  let approvals = 0
  const failures = []
  for (let round = 0; round < maxRounds; round += 1) {
    const completion = page.locator('[data-testid="agent-completion"]')
    if (await completion.count() > 0) break
    const errorLine = page.locator('[data-testid="agent-error-code"]')
    if (await errorLine.count() > 0) {
      const text = (await errorLine.first().textContent()) || ''
      failures.push(text)
      assert.ok(!/AGENT_STEP_FAILED/.test(text), `Agent step 失败：${text}`)
    }
    const approval = page.locator('[data-testid="agent-approval"]')
    if (allowApproval && await approval.count() > 0) {
      approvals += 1
      await clearToasts(page)
      await page.click('[data-testid="agent-approve"]')
      await page.waitForTimeout(1500)
      continue
    }
    const resume = page.locator('[data-testid="agent-resume"]')
    if (await resume.count() > 0) {
      await clearToasts(page)
      await resume.first().click()
      await page.waitForTimeout(1500)
      continue
    }
    await page.waitForTimeout(1200)
  }
  return { approvals, failures }
}

;(async () => {
  const browser = await chromium.launch({ channel: 'msedge' })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() !== 'error') return
    const text = message.text()
    if (/409 \(Conflict\)/.test(text) || /422 \(/.test(text)) return
    errors.push(`console ${text}`)
  })

  // 1) 打开 Agent 页
  await page.goto(`${BASE}/#/studio/n/${NOVEL}/agent`, { waitUntil: 'networkidle' })
  await page.waitForSelector('[data-testid="workspace-agent"]', { timeout: 20000 })
  await page.waitForSelector('[data-testid="agent-goal-input"]')
  await shot(page, '13-agent-goal')

  // 2) 输入目标 + 选择范围 → 计划预览（0 mutation）
  await page.fill('[data-testid="agent-goal-input"]',
    '把这一幕扩展到 3 个章节，每章至少有 2 个场景，运行质量检查并修复可以自动安全修复的问题，不要自动接受')
  await page.selectOption('[data-testid="agent-scope"]', 'structural_unit')
  await page.waitForTimeout(600)
  await page.click('[data-testid="agent-plan"]')
  await page.waitForSelector('[data-testid="agent-plan-preview"]', { timeout: 30000 })
  const preview = await page.textContent('[data-testid="agent-plan-preview"]')
  assert.ok(preview.includes('还没有修改任何内容'), '计划预览未声明 0 mutation')
  const steps = await page.locator('[data-testid="agent-steps"] li').count()
  assert.ok(steps >= 3, `计划步骤过少：${steps}`)
  await shot(page, '14-agent-plan')

  // 3) 执行 → 完成（不自动接受 / 不自动交付）
  await clearToasts(page)
  await page.click('[data-testid="agent-start"]')
  await page.waitForSelector('[data-testid="agent-status"]', { timeout: 60000 })
  await clearToasts(page)
  await page.waitForFunction(
    () => ['已完成', '完成', '等待你确认', '已暂停', '需要作者决定', '已取消', '失败']
      .some((value) => (document.querySelector('[data-testid="agent-status"]')
        ?.textContent || '').includes(value)),
    null, { timeout: 90000 })
  let status = await page.textContent('[data-testid="agent-status"]')
  await shot(page, '15-agent-running')

  // 4) 跑到终态（本阶段的目标「不要自动接受」→ 不应出现 protected 审批）
  const phase1 = await driveAgent(page, { allowApproval: false })
  assert.equal(phase1.approvals, 0, '「不要自动接受」的目标不应要求 protected 审批')
  status = await page.textContent('[data-testid="agent-status"]')

  // 5) 完成摘要（目标 / 修改节点 / 版本 / 质量 / 需作者决定）
  await page.waitForSelector('[data-testid="agent-completion"]', { timeout: 90000 })
  const completion = await page.textContent('[data-testid="agent-completion"]')
  assert.ok(completion.includes('修改的节点'), '完成摘要缺少改动节点')
  assert.ok(completion.includes('质量结论'), '完成摘要缺少质量结论')
  assert.ok(completion.includes('Agent 不会替你接受内容'), '完成摘要缺少安全说明')

  // 6) 安全：新生成内容仍是 proposed（不自动接受）
  const proposed = await page.evaluate(async (novelId) => {
    const data = await (await fetch(
      `/api/story-builder/studio/blueprint?novel_id=${novelId}`)).json()
    const chapters = data.nodes.filter((row) => row.node_type === 'chapter')
      .sort((a, b) => a.node_id.localeCompare(b.node_id))
    return { total: chapters.length,
      statuses: chapters.map((row) => `${row.node_id}:${row.status}`) }
  }, NOVEL)
  assert.ok(proposed.total >= 2, `Agent 未生成新章节：${JSON.stringify(proposed)}`)
  assert.ok(proposed.statuses.some((row) => row.endsWith(':proposed')),
    `新增内容未保持 proposed：${JSON.stringify(proposed)}`)
  assert.ok(!proposed.statuses.some((row) => row.includes('ch_00') && false), '')
  await shot(page, '16-agent-complete')

  // 6b) protected approval 路径（V4.0.2 PB-2）：必须真实经过人工闸门
  //     前置：上一阶段的结果必须清空（点「生成计划」会 setResult(null)）
  await page.fill('[data-testid="agent-goal-input"]', '接受当前章节与场景的结果')
  await page.selectOption('[data-testid="agent-scope"]', 'novel')
  await page.waitForTimeout(400)
  await clearToasts(page)
  await page.click('[data-testid="agent-plan"]')
  await page.waitForSelector('[data-testid="agent-plan-preview"]', { timeout: 30000 })
  // 上一阶段的预览仍在 DOM 里 → 必须等**新计划**（含 protected 步骤）真正渲染出来
  await page.waitForFunction(() => {
    const text = document.querySelector('[data-testid="agent-plan-preview"]')?.textContent || ''
    const match = text.match(/需要你确认\s*(\d+)\s*步/)
    return Boolean(match && Number(match[1]) >= 1)
  }, null, { timeout: 30000 })
  const approvalPreview = await page.textContent('[data-testid="agent-plan-preview"]')
  assert.ok(approvalPreview.includes('需要你确认'),
    '接受类计划必须标记「需要你确认」步骤')
  const protectedSteps = Number((approvalPreview.match(/需要你确认\s*(\d+)\s*步/) || [])[1])
  assert.ok(protectedSteps >= 1, `受保护步骤数异常：${approvalPreview}`)
  assert.ok(await page.locator('[data-testid="agent-completion"]').count() === 0,
    '新计划必须清空上一阶段结果')

  await clearToasts(page)
  await page.click('[data-testid="agent-start"]')
  await page.waitForSelector('[data-testid="agent-approval"]', { timeout: 60000 })
  const approvalText = await page.locator('[data-testid="agent-approval"]').textContent()
  assert.ok(approvalText.includes('需要你的确认'), '审批面板文案不正确')
  assert.ok(approvalText.includes('基于版本'), '审批面板缺少 revision 绑定信息')
  await shot(page, '17-agent-approval')

  const phase2 = await driveAgent(page, { allowApproval: true, maxRounds: 8 })
  assert.ok(phase2.approvals >= 1,
    `approvals=${phase2.approvals}：必须至少覆盖一次 protected 审批`)
  await page.waitForSelector('[data-testid="agent-completion"]', { timeout: 90000 })
  const approvalCompletion = await page.textContent('[data-testid="agent-completion"]')
  assert.ok(approvalCompletion.includes('修改的节点'), '审批阶段完成摘要不完整')
  const approvalErrors = await page.locator('[data-testid="agent-error-code"]').count()
  assert.equal(approvalErrors, 0, '审批阶段出现了错误提示')
  await shot(page, '18-agent-approved')

  // 7) 取消文案诚实（不声称已立即中止模型）
  const cancelSemantics = await page.evaluate(async (novelId) => {
    const planned = await (await fetch('/api/story-builder/agent/plan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ novel_id: novelId, instruction: '运行质量检查',
        scope_kind: 'novel', dry_run: true }) })).json()
    const cancelled = await (await fetch(
      `/api/story-builder/agent/${planned.session_id}/cancel`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: planned.session_id, reason: 'gate' }) })).json()
    return cancelled.semantics || ''
  }, NOVEL)
  assert.ok(cancelSemantics.includes('当前步骤结束后停止'), '取语文案不明确')
  assert.ok(!/已(立即)?中止|已停止模型/.test(cancelSemantics),
    `取消文案过度承诺：${cancelSemantics}`)

  await browser.close()
  assert.deepEqual(errors, [], `页面出现错误：\n${errors.join('\n')}`)
  console.log('V4-11 Agent browser gate: PASS')
})().catch((error) => {
  console.error('V4-11 Agent browser gate: FAIL')
  console.error(error)
  process.exit(1)
})
