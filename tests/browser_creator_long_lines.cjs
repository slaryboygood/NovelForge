// V2-J-05 长线浏览器验收：三题材各跑一次长线后，创作者面板必须显示 StoryState 的真实长期数据。
// 只连接隔离测试服务（默认 8012，临时数据根目录），不操作正式作者存档。
const { chromium, request } = require('playwright')
const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const path = require('node:path')

const BASE = process.env.STORY_TEST_URL || 'http://127.0.0.1:8012'
const PACKS = (process.env.STORY_PACK_IDS || 'xianxia_demo,sci_fi_demo,mystery_demo').split(',')
const CHAPTERS = Number(process.env.STORY_LONG_CHAPTERS || 22)
const PROJECT_ROOT = path.resolve(__dirname, '..')
const PYTHON = path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe')

async function createStory(http, packId, novelId) {
  const created = await http.post('/api/story-builder/novels',
    { data: { novel_id: novelId, title: novelId, content_pack_id: packId } })
  assert.equal(created.status(), 201, await created.text())
  const session = await (await http.post('/api/story-builder/sessions', { data: { project_id: novelId } })).json()
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
  return bp
}

async function runJourney(http, bp, steps = 3) {
  const base = '/api/story-builder/blueprints/' + bp.blueprint_id + '/adventures/' + bp.version
  let scene = await (await http.post(base)).json()
  for (let i = 0; i < steps; i += 1) {
    if (!scene.choices.length) break
    const next = await http.post(base + '/choices',
      { data: { revision: scene.state.revision, choice_id: scene.choices[0].id } })
    assert.equal(next.status(), 200, await next.text())
    scene = await next.json()
  }
  return scene
}

;(async () => {
  const http = await request.newContext({ baseURL: BASE })
  const health = await (await http.get('/api/health')).json()
  const dataRoot = health.root
  assert.ok(dataRoot, '测试服务必须暴露隔离数据根目录')
  const stamp = String(Date.now() % 1000000)
  const novels = []
  for (const [index, pack] of PACKS.entries()) {
    const novelId = 'novel_long_' + pack + '_' + stamp + '_' + index
    const bp = await createStory(http, pack, novelId)
    await runJourney(http, bp)
    // 用同一套引擎函数铺开长线（22 章 + 世界自主行动 + 世界事件）。
    const seeded = execFileSync(PYTHON, [path.join(PROJECT_ROOT, 'scripts', 'seed_long_line_state.py'),
      '--root', dataRoot, '--novel', novelId, '--pack', pack], { encoding: 'utf-8' })
    assert.ok(seeded.includes('seeded'), '长线种子失败：' + seeded)
    const world = await (await http.get('/api/story-builder/creator/world?novel_id=' + novelId)).json()
    assert.equal(world.meta.persisted, true, pack + ' 推演后必须存在 StoryState')
    const linkage = await (await http.get('/api/story-builder/creator/linkage?novel_id=' + novelId)).json()
    assert.ok(linkage.counts.happened >= CHAPTERS, pack + ' 长线应至少有 ' + CHAPTERS + ' 条已发生记录')
    assert.ok(linkage.long_line.volumes.length >= 3, pack + ' 长线应至少 3 卷')
    novels.push({ pack, novelId, world })
  }

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    const failures = []
    page.on('response', (response) => {
      // /sessions/latest 与 /blueprint 在没有会话或蓝图时返回 404 属于正常空状态。
      if (response.status() >= 400
          && !response.url().includes('/sessions/latest')
          && !response.url().endsWith('/blueprint')) {
        failures.push(response.status() + ' ' + response.url())
      }
    })
    await page.goto(BASE)
    for (const novel of novels) {
      await page.getByLabel('小说', { exact: true }).selectOption(novel.novelId)
      for (const tab of ['世界面板', '角色面板', '剧情面板', '成长面板', '记忆面板', '导演面板', '大纲联动']) {
        await page.getByRole('tab', { name: tab }).click()
        const panel = page.locator('.world-panel').first()
        await panel.locator('.world-panel-head').waitFor({ timeout: 20000 })
        const text = await panel.innerText()
        assert.ok(text.includes('StoryState 已存档'), novel.pack + ' / ' + tab + ' 必须显示已存档事实')
        if (tab === '世界面板') {
          assert.ok(text.includes(String(novel.world.timeline.tick)), '世界面板必须显示真实 tick')
          assert.ok(text.includes('势力状态'), '世界面板必须显示势力状态')
        }
        if (tab === '大纲联动') {
          const linkage = await (await http.get('/api/story-builder/creator/linkage?novel_id=' + novel.novelId)).json()
          assert.ok(text.includes('happened · ' + linkage.counts.happened), '大纲联动必须显示真实已发生路线')
          assert.ok(text.includes('卷 ' + linkage.long_line.volumes.length), '大纲联动必须显示真实卷数')
        }
      }
    }
    // 手机宽度：三题材长线状态下面板仍不横向溢出。
    await page.setViewportSize({ width: 390, height: 844 })
    for (const tab of ['世界面板', '记忆面板', '大纲联动']) {
      await page.getByRole('tab', { name: tab }).click()
      await page.waitForTimeout(200)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false,
        tab + ' 在手机宽度出现横向溢出')
    }
    assert.deepEqual(failures, [], '接口不应失败：' + failures.join(' | '))
    console.log('通过：三题材长线创作者面板 / 真实 StoryState / 手机宽度。')
  } finally {
    await browser.close()
    await http.dispose()
  }
})().catch(error => { console.error(error); process.exitCode = 1 })
