// W4 Edge 实机验收：版本列表 → 联动影响 → 改写（生成新版本）→ 版本对比 → 回退 → 导出 JSON/DOCX。
// 只连接隔离测试服务（STORY_TEST_URL），不操作正式作者存档。
const { chromium, request } = require('playwright')
const assert = require('node:assert/strict')

const BASE = process.env.STORY_TEST_URL || 'http://127.0.0.1:8020'
const IDEA = '一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。'

async function prepared(http, novelId) {
  assert.equal((await http.post('/api/story-builder/novels',
    { data: { novel_id: novelId, title: novelId } })).status(), 201)
  assert.equal((await http.put('/api/story-builder/creative/brief?novel_id=' + novelId,
    { data: { original_idea: IDEA, selected_genre: 'xianxia', tone: '紧张悬疑' } })).status(), 200)
  const seed = (await (await http.post(
    '/api/story-builder/settings/seed?novel_id=' + novelId, { data: {} })).json()).seed
  assert.equal((await http.put('/api/story-builder/settings/seed?novel_id=' + novelId,
    { data: { seed, selected: seed.selected } })).status(), 200)
  assert.equal((await http.post('/api/story-builder/runtime/start?novel_id=' + novelId,
    { data: {} })).status(), 200)
  for (let index = 0; index < 8; index += 1) {
    const state = await (await http.get(
      '/api/story-builder/runtime/state?novel_id=' + novelId)).json()
    const available = state.candidates.filter((row) => row.available).map((row) => row.action_id)
    if (!available.length) break
    const moved = await http.post('/api/story-builder/runtime/advance?novel_id=' + novelId,
      { data: { action_id: available[index % available.length],
                expected_revision: state.revision } })
    assert.equal(moved.status(), 200, await moved.text())
  }
  assert.equal((await http.post('/api/story-builder/outline/forge?novel_id=' + novelId,
    { data: { volumes: 3, arcs_per_volume: 2, chapters_per_arc: 5 } })).status(), 200)
  assert.equal((await http.post('/api/story-builder/outline/confirm?novel_id=' + novelId,
    { data: {} })).status(), 200)
}

;(async () => {
  const http = await request.newContext({ baseURL: BASE })
  const novelId = 'novel_rev_' + (Date.now() % 1000000)
  await prepared(http, novelId)

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
    await page.goto(BASE)
    await page.getByLabel('小说', { exact: true }).selectOption(novelId)
    await page.getByRole('button', { name: '开始构筑' }).click()
    await page.getByRole('tab', { name: '大纲锻造' }).waitFor({ timeout: 20000 })
    await page.getByRole('tab', { name: '大纲锻造' }).click()
    const panel = page.locator('.outline-forge-panel')
    await panel.getByText('版本与联动 · W4').waitFor({ timeout: 30000 })

    // 切到一个卷包，检查版本列表。
    const packageSelect = panel.getByLabel('版本大纲包')
    const optionValues = await packageSelect.locator('option').evaluateAll(
      (nodes) => nodes.map((node) => node.value))
    const volumeValue = optionValues.find((value) => value.endsWith('_vol01'))
    assert.ok(volumeValue, '应能选择卷包：' + optionValues.slice(0, 3).join(','))
    await packageSelect.selectOption(volumeValue)
    await panel.getByText('V1 · CONFIRMED').waitFor({ timeout: 20000 })
    const versionText = await panel.innerText()
    assert.ok(versionText.includes('与上一版对比'), '版本列表必须提供对比入口')
    assert.ok(versionText.includes('回退到此版本'), '版本列表必须提供回退入口')

    // 联动影响：改卷目标会影响下游篇章 / 章节，已发生事实只提示。
    await panel.getByRole('button', { name: '查看联动影响' }).click()
    await panel.getByText(/下游受影响 \d+ 个包/).waitFor({ timeout: 20000 })
    const impactText = await panel.innerText()
    assert.ok(/已发生事实 \d+ 条/.test(impactText), '必须展示被波及的已发生事实')
    assert.ok(/规划内容 \d+ 条/.test(impactText), '必须展示受影响的规划内容')

    // 改写 → 生成新版本 V2，并且来源与已确认历史不受影响。
    await panel.getByLabel('改写字段').selectOption('summary')
    await panel.getByLabel('改写内容').fill('作者改写的卷目标')
    await panel.getByRole('button', { name: '改写并查看影响' }).click()
    await panel.getByText(/已改写 .*新版本 V2/).waitFor({ timeout: 30000 })
    await panel.getByText('V2 · DRAFT').waitFor({ timeout: 20000 })
    const chain = await (await http.get(
      '/api/story-builder/outline/chain?novel_id=' + novelId)).json()
    assert.equal(chain.book.status, 'CONFIRMED')
    assert.equal(chain.volumes[0].status, 'DRAFT')
    assert.equal(chain.volumes[0].version, 2)
    assert.equal(chain.volumes[0].items[0].summary, '作者改写的卷目标')

    // 版本对比与回退。
    const secondRow = panel.locator('.world-row').filter({ hasText: 'V2 · DRAFT' }).first()
    await secondRow.getByRole('button', { name: '与上一版对比' }).click()
    await panel.getByText(/V1 → V2：1 个条目有差异/).waitFor({ timeout: 20000 })
    const diffText = await panel.innerText()
    assert.ok(diffText.includes('summary'), '对比必须指出改了哪个字段')
    await secondRow.getByRole('button', { name: '回退到此版本' }).click()
    await panel.getByText(/已按 V2 生成新版本 V3/).waitFor({ timeout: 20000 })

    // 导出 JSON / DOCX。
    await panel.getByRole('button', { name: '导出 JSON' }).click()
    await panel.getByText(/已导出 .*\.json/).waitFor({ timeout: 30000 })
    await panel.getByRole('button', { name: '导出 DOCX' }).click()
    await panel.getByText(/已导出 .*\.docx/).waitFor({ timeout: 30000 })

    // 刷新恢复。
    await page.reload()
    await page.getByLabel('小说', { exact: true }).selectOption(novelId)
    const tab = page.getByRole('tab', { name: '大纲锻造' })
    if (await tab.count() === 0) {
      await page.getByRole('button', { name: '开始构筑' }).click()
    }
    await tab.click()
    await page.locator('.outline-forge-panel').getByText('版本与联动 · W4')
      .waitFor({ timeout: 30000 })

    // 手机宽度不得横向溢出
    await page.setViewportSize({ width: 390, height: 844 })
    await page.locator('.outline-forge-panel').waitFor()
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false,
      '手机宽度不得横向溢出')
    console.log('通过：版本 / 联动影响 / 改写 / 对比 / 回退 / 导出 / 刷新 / 手机宽度。')
  } finally {
    await browser.close()
    await http.dispose()
  }
})().catch(error => { console.error(error); process.exitCode = 1 })
