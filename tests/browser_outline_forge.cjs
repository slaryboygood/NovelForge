// W3 Edge 实机验收：剧情路线 → 预览结构 → 锻造四级大纲 → 章纲字段 → 确认 → 导出 → 刷新恢复。
// 只连接隔离测试服务（STORY_TEST_URL），不操作正式作者存档。
const { chromium, request } = require('playwright')
const assert = require('node:assert/strict')

const BASE = process.env.STORY_TEST_URL || 'http://127.0.0.1:8020'
const IDEA = '一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。'

;(async () => {
  const http = await request.newContext({ baseURL: BASE })
  const novelId = 'novel_forge_' + (Date.now() % 1000000)
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
  for (let index = 0; index < 10; index += 1) {
    const state = await (await http.get(
      '/api/story-builder/runtime/state?novel_id=' + novelId)).json()
    const available = state.candidates.filter((row) => row.available).map((row) => row.action_id)
    if (!available.length) break
    const moved = await http.post('/api/story-builder/runtime/advance?novel_id=' + novelId,
      { data: { action_id: available[index % available.length],
                expected_revision: state.revision } })
    assert.equal(moved.status(), 200, await moved.text())
  }

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
    await page.goto(BASE)
    await page.getByLabel('小说', { exact: true }).selectOption(novelId)
    await page.getByRole('button', { name: '开始构筑' }).click()
    await page.getByRole('tab', { name: '大纲锻造' }).waitFor({ timeout: 20000 })
    await page.getByRole('tab', { name: '大纲锻造' }).click()
    const panel = page.locator('.outline-forge-panel')
    await panel.waitFor({ timeout: 20000 })

    await panel.getByRole('button', { name: '预览结构' }).click()
    await panel.getByText(/预览：3 卷 \/ 6 篇章 \/ 30 章/).waitFor({ timeout: 30000 })
    const previewText = await panel.innerText()
    assert.ok(previewText.includes('质量评估'), '预览必须给出质量评估')
    assert.ok(previewText.includes('详细章纲 · 30 章'), '预览必须列出 30 章')

    await panel.getByRole('button', { name: '锻造四级大纲' }).click()
    await panel.getByText(/已锻造 3 卷 \/ 6 篇章 \/ 30 章/).waitFor({ timeout: 30000 })
    const forged = await (await http.get(
      '/api/story-builder/outline/chain?novel_id=' + novelId)).json()
    assert.equal(forged.fresh, true)
    assert.equal(forged.volumes.length, 3)
    assert.equal(forged.arcs.length, 6)
    assert.equal(forged.chapters.length, 30)
    assert.ok(forged.quality.ok, JSON.stringify(forged.quality.findings))

    // 章纲必须能直接支撑写作：展开一章并核对关键字段都来自引擎。
    const firstChapter = panel.locator('details').filter({ hasText: '第1章' }).first()
    await firstChapter.locator('summary').click()
    const chapterText = await firstChapter.innerText()
    for (const label of ['本章目标', '核心冲突', '开场状态', '本章结果', '结尾钩子',
      '来源事实', '不得违反']) {
      assert.ok(chapterText.includes(label), '章纲缺少字段：' + label)
    }
    assert.ok(/route_\d+/.test(chapterText), '已发生章节必须带来源记录')
    assert.ok(/来源事实：route_\d+/.test(chapterText), '章纲必须标注来源事实')

    await panel.getByRole('button', { name: '确认整条大纲' }).click()
    await panel.getByText(/已按顺序确认 \d+ 个大纲层/).waitFor({ timeout: 30000 })
    const confirmed = await (await http.get(
      '/api/story-builder/outline/chain?novel_id=' + novelId)).json()
    assert.equal(confirmed.book.status, 'CONFIRMED')
    assert.equal(confirmed.chapters[0].status, 'CONFIRMED')

    await panel.getByRole('button', { name: '导出 Markdown' }).click()
    await panel.getByText(/已导出/).waitFor({ timeout: 30000 })
    const exportContent = await panel.locator('.outline-export-preview').innerText()
    assert.ok(exportContent.includes('不得违反'), '导出必须包含约束')
    assert.ok(exportContent.includes('结尾钩子'), '导出必须包含钩子')

    // 刷新恢复：大纲链不依赖前端缓存。
    await page.reload()
    await page.getByLabel('小说', { exact: true }).selectOption(novelId)
    const tab = page.getByRole('tab', { name: '大纲锻造' })
    if (await tab.count() === 0) {
      await page.getByRole('button', { name: '开始构筑' }).click()
    }
    await tab.click()
    await page.locator('.outline-forge-panel').getByText(/全书主线/).waitFor({ timeout: 30000 })
    await page.locator('.outline-forge-panel').getByText('来源一致').first()
      .waitFor({ timeout: 30000 })
    const afterReload = await page.locator('.outline-forge-panel').innerText()
    const badge = await page.locator('.outline-forge-panel .badge').first().innerText()
    assert.ok(badge.includes('来源一致'), '刷新后 badge=' + badge)
    assert.ok(afterReload.includes('详细章纲 · 30 章'), '刷新后仍应列出 30 章')

    // 手机宽度不得横向溢出
    await page.setViewportSize({ width: 390, height: 844 })
    await page.locator('.outline-forge-panel').waitFor()
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false,
      '手机宽度不得横向溢出')
    console.log('通过：预览结构 / 锻造四级大纲 / 章纲字段 / 确认 / 导出 / 刷新 / 手机宽度。')
  } finally {
    await browser.close()
    await http.dispose()
  }
})().catch(error => { console.error(error); process.exitCode = 1 })
