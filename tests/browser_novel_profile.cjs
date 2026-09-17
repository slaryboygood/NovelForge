// 只连接隔离测试服务（默认 8012，使用临时数据根目录）；不操作正式作者存档。
const { chromium, request } = require('playwright')
const assert = require('node:assert/strict')
;(async () => {
  const base = process.env.STORY_TEST_URL || 'http://127.0.0.1:8012'
  const http = await request.newContext({ baseURL: base })
  const alpha = await (await http.post('/api/story-builder/novels',
    { data: { novel_id: 'novel_alpha', title: '甲书', genre: 'xianxia' } })).json()
  assert.equal(alpha.novel.title, '甲书')
  const beta = await (await http.post('/api/story-builder/novels',
    { data: { novel_id: 'novel_beta', title: '乙书', genre: 'sci_fi' } })).json()
  assert.equal(beta.novel.novel_id, 'novel_beta')
  const alphaSession = await (await http.post('/api/story-builder/sessions',
    { data: { project_id: 'novel_alpha' } })).json()
  const betaSession = await (await http.post('/api/story-builder/sessions',
    { data: { project_id: 'novel_beta' } })).json()
  assert.equal(alphaSession.novel.novel_id, 'novel_alpha')
  assert.equal(betaSession.novel.novel_id, 'novel_beta')

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await page.goto(base)
    // 小说是刚创建的：刷新一次保证列表里已经包含它们。
    await page.reload()
    await page.locator('.story-builder-empty, .story-builder-page').waitFor({ timeout: 20000 })
    await page.getByLabel('小说').first().waitFor({ state: 'visible', timeout: 20000 })
    await page.getByLabel('小说').first().selectOption('novel_alpha')
    await page.getByText(/小说：甲书/).waitFor({ timeout: 20000 })
    await page.getByLabel('小说').first().selectOption('novel_beta')
    await page.getByText(/小说：乙书/).waitFor()
    await page.reload()
    await page.getByText(/小说：乙书/).waitFor()
    assert.equal(await page.getByLabel('小说').first().inputValue(), 'novel_beta')

    // 在乙书里做一次选择，切回甲书后新会话版本不受影响。
    const alphaUrl = '/api/story-builder/sessions/' + alphaSession.session.session_id
    const betaUrl = '/api/story-builder/sessions/' + betaSession.session.session_id
    await http.post(betaUrl + '/selections', { data: { step: 'reader_experience',
      option_ids: ['experience_growth_adventure'], expected_selection_version: 0 } })
    await page.getByLabel('小说').selectOption('novel_alpha')
    await page.getByText(/小说：甲书/).waitFor()
    assert.equal((await (await http.get(alphaUrl)).json()).session.selection_version, 0)
    assert.equal((await (await http.get(betaUrl)).json()).session.selection_version, 1)

    await page.setViewportSize({ width: 390, height: 844 })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
    await page.screenshot({ path: process.env.STORY_TEST_SHOT || 'workspace/novel-switch.png' })
    console.log('通过：小说切换、刷新恢复、跨小说状态隔离与手机宽度。')
  } finally { await browser.close(); await http.dispose() }
})().catch(error => { console.error(error); process.exitCode = 1 })
