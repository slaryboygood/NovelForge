// V2-I 持久化路线验收：真实推演 3 次选择后，七个面板必须显示 StoryState 已存档的数据。
// 只连接隔离测试服务（默认 8012，临时数据根目录），不操作正式作者存档。
const { chromium, request } = require('playwright')
const assert = require('node:assert/strict')

const BASE = process.env.STORY_TEST_URL || 'http://127.0.0.1:8012'
const PACK_ID = process.env.STORY_PACK_ID || 'xianxia_demo'

;(async () => {
  const http = await request.newContext({ baseURL: BASE })
  const novelId = 'novel_persisted_' + (Date.now() % 1000000)
  const created = await http.post('/api/story-builder/novels',
    { data: { novel_id: novelId, title: novelId, content_pack_id: PACK_ID } })
  assert.equal(created.status(), 201, await created.text())
  const session = await (await http.post('/api/story-builder/sessions',
    { data: { project_id: novelId } })).json()
  const url = '/api/story-builder/sessions/' + session.session.session_id
  const catalog = await (await http.get('/api/story-builder/catalogs')).json()
  for (const [version, step] of catalog.steps.entries()) {
    const rec = await (await http.post(url + '/recommendations', { data: { step: step.step } })).json()
    const saved = await http.post(url + '/selections', { data: { step: step.step,
      option_ids: [rec.recommendation.recommendations[0].option_id], expected_selection_version: version } })
    assert.equal(saved.status(), 200, await saved.text())
  }
  const bp = (await (await http.post(url + '/compile-blueprint')).json()).blueprint
  const confirmed = await http.post('/api/story-builder/blueprints/' + bp.blueprint_id + '/confirm',
    { data: { version: bp.version } })
  assert.equal(confirmed.status(), 200, await confirmed.text())
  const base = '/api/story-builder/blueprints/' + bp.blueprint_id + '/adventures/' + bp.version
  let scene = await (await http.post(base)).json()
  for (let i = 0; i < 3; i += 1) {
    assert.ok(scene.choices.length > 0, '第 ' + (i + 1) + ' 步应有可选行动')
    const next = await http.post(base + '/choices',
      { data: { revision: scene.state.revision, choice_id: scene.choices[0].id } })
    assert.equal(next.status(), 200, await next.text())
    scene = await next.json()
  }
  const worldApi = await (await http.get('/api/story-builder/creator/world?novel_id=' + novelId)).json()
  assert.equal(worldApi.meta.persisted, true, '推演后必须存在 StoryState 存档')

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    const failures = []
    page.on('response', (response) => {
      if (response.status() >= 400 && !response.url().includes('/sessions/latest')) {
        failures.push(response.status() + ' ' + response.url())
      }
    })
    await page.goto(`${BASE}/?ui=v2`)
    await page.getByLabel('小说', { exact: true }).selectOption(novelId)
    const checks = [
      ['世界面板', '世界正在发生什么', (text, api) => text.includes(String(api.timeline.tick))],
      ['角色面板', '人物正在变成什么样', (text, api) => text.includes(api.detail.name)],
      ['剧情面板', '现在能做什么、会发生什么', (text, api) => text.includes('available ' + api.available.length)],
      ['成长面板', '七类成长在同一套 Progression 上', (text, api) => text.includes('已拥有 ' + (api.counts.owned || 0))],
      ['记忆面板', '谁知道什么，还欠什么没解决', (text, api) => text.includes('未回收伏笔 · ' + api.open_foreshadows.length)],
      ['导演面板', '为什么推荐这个事件', (text, api) => text.includes(api.chosen_title || '暂无')],
      ['大纲联动', '从已发生的事实长到全书', (text, api) => text.includes('happened · ' + api.counts.happened)],
    ]
    const endpoints = ['world', 'characters', 'plot', 'progression', 'memory', 'director', 'linkage']
    for (const [index, [tab, heading, verify]] of checks.entries()) {
      await page.getByRole('tab', { name: tab }).click()
      const panel = page.locator('.world-panel').first()
      await panel.getByText(heading).waitFor({ timeout: 20000 })
      const api = await (await http.get('/api/story-builder/creator/' + endpoints[index]
        + '?novel_id=' + novelId)).json()
      assert.equal(api.meta.persisted, true, tab + ' 必须显示已存档事实')
      const text = await panel.innerText()
      assert.ok(text.includes('StoryState 已存档'), tab + ' 必须标注已存档')
      assert.ok(verify(text, api), tab + ' 显示的数据必须与 API 一致')
    }
    // 刷新恢复：重新载入后仍然读取同一份事实。
    await page.reload()
    await page.getByLabel('小说', { exact: true }).selectOption(novelId)
    await page.getByRole('tab', { name: '大纲联动' }).waitFor({ timeout: 20000 })
    await page.getByRole('tab', { name: '大纲联动' }).click()
    await page.locator('.world-panel').first().getByText('从已发生的事实长到全书').waitFor({ timeout: 20000 })
    await page.getByRole('tab', { name: '世界面板' }).click()
    await page.locator('.world-panel').first().getByText('世界正在发生什么').waitFor({ timeout: 20000 })
    const afterReload = await (await http.get('/api/story-builder/creator/world?novel_id=' + novelId)).json()
    assert.deepEqual(afterReload.timeline, worldApi.timeline)
    // 手机宽度：七个面板都不横向溢出。
    await page.setViewportSize({ width: 390, height: 844 })
    for (const [tab] of checks) {
      await page.getByRole('tab', { name: tab }).click()
      await page.waitForTimeout(200)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false,
        tab + ' 在手机宽度出现横向溢出')
    }
    assert.deepEqual(failures, [], '接口不应失败：' + failures.join(' | '))
    console.log('通过：持久化路线七面板与 StoryState 一致 / 刷新恢复 / 手机宽度。')
  } finally {
    await browser.close()
    await http.dispose()
  }
})().catch(error => { console.error(error); process.exitCode = 1 })
