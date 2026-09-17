// 每个题材各跑一次完整 UI 流程：新建小说 → 选内容包 → 创建故事 → 选择 → 状态变化 → 大纲 → 刷新恢复。
const { chromium, request } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const base = process.env.STORY_TEST_URL || 'http://127.0.0.1:8012'
  const packId = process.env.STORY_PACK_ID || 'journey_v1'
  const novelId = process.env.STORY_NOVEL_ID || ('novel_' + packId.replace(/[^a-z0-9_]/g, '_') + '_' + (Date.now() % 100000))
  const http = await request.newContext({ baseURL: base })
  const created = await http.post('/api/story-builder/novels',
    { data: { novel_id: novelId, title: novelId, content_pack_id: packId } })
  assert.equal(created.status(), 201, await created.text())
  const novel = (await created.json()).novel
  assert.equal(novel.content_pack_id, packId)
  const session = await (await http.post('/api/story-builder/sessions',
    { data: { project_id: novelId } })).json()
  const url = '/api/story-builder/sessions/' + session.session.session_id
  const catalog = await (await http.get('/api/story-builder/catalogs')).json()
  for (const [version, step] of catalog.steps.entries()) {
    const rec = await (await http.post(url + '/recommendations', { data: { step: step.step } })).json()
    const saved = await http.post(url + '/selections', { data: { step: step.step,
      option_ids: [rec.recommendation.recommendations[0].option_id], expected_selection_version: version } })
    assert.equal(saved.status(), 200)
  }
  const bp = await (await http.post(url + '/compile-blueprint')).json()
  await http.post('/api/story-builder/blueprints/' + bp.blueprint.blueprint_id + '/confirm',
    { data: { version: bp.blueprint.version } })

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    const consoleErrors = []
    page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
    page.on('pageerror', (error) => consoleErrors.push('pageerror: ' + error.message))
    await page.goto(base)
    await page.getByLabel('小说', { exact: true }).selectOption(novelId)
    await page.getByRole('button', { name: '开始 / 继续旅程' }).click()
    const firstTitle = await page.locator('.adventure-panel h3, .adventure-panel h2').first().innerText()
    for (let i = 0; i < 3; i += 1) {
      const buttons = page.locator('.adventure-choices button')
      await buttons.first().waitFor({ timeout: 20000 })
      assert.ok(await buttons.count() > 0, '第 ' + (i + 1) + ' 步应有可选行动')
      await buttons.first().click()
    }
    try {
      await page.getByRole('heading', { name: '本段旅程结束' }).waitFor({ timeout: 15000 })
    } catch (error) {
      const shot = process.env.STORY_TEST_SHOT || 'workspace/genre-failure.png'
      await page.screenshot({ path: shot })
      console.error('DIAG url=' + page.url())
      console.error('DIAG panel=' + JSON.stringify(await page.locator('.adventure-panel').innerText().catch(() => '<no panel>')))
      console.error('DIAG headings=' + JSON.stringify(await page.locator('h2, h3').allInnerTexts().catch(() => [])))
      console.error('DIAG buttons=' + JSON.stringify(await page.locator('button').allInnerTexts().catch(() => [])))
      console.error('DIAG console=' + JSON.stringify(consoleErrors.slice(0, 5)))
      console.error('DIAG shot=' + shot)
      throw error
    }
    await page.getByRole('button', { name: '用当前路线整合大纲', exact: true }).click()
    await page.getByText(/当前路线只覆盖实际推演的阶段/).first().waitFor()
    await page.reload()
    await page.getByText(new RegExp('小说：' + novelId)).waitFor()
    const resume = page.getByRole('button', { name: '开始 / 继续旅程' })
    if (await resume.count() > 0) await resume.first().click()
    await page.getByRole('button', { name: '用当前路线整合大纲', exact: true }).waitFor()
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
    console.log('通过：' + packId + ' 完整 UI 流程（首场景：' + firstTitle + '）')
  } finally { await browser.close(); await http.dispose() }
})().catch(error => { console.error(error); process.exitCode = 1 })



