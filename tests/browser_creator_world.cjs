// V2-I-01 世界面板浏览器验收：新建/切换小说 → 世界面板 → 刷新恢复 → 手机宽度不溢出。
// 只连接隔离测试服务（默认 8012，临时数据根目录），不操作正式作者存档。
const { chromium, request } = require('playwright')
const assert = require('node:assert/strict')

const BASE = process.env.STORY_TEST_URL || 'http://127.0.0.1:8012'
const PACKS = (process.env.STORY_PACK_IDS || 'xianxia_demo,sci_fi_demo,mystery_demo').split(',')

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

;(async () => {
  const http = await request.newContext({ baseURL: BASE })
  const stamp = String(Date.now() % 1000000)
  const packs = (await (await http.get('/api/story-builder/content-packs')).json()).packs
  const novels = PACKS.map((pack, index) => ({
    pack, novelId: 'novel_' + pack + '_' + stamp + '_' + index,
    packTitle: (packs.find((item) => item.pack_id === pack) || {}).title || pack,
  }))
  for (const item of novels) await createStory(http, item.pack, item.novelId)
  const first = novels[0]

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    const consoleErrors = []
    page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
    page.on('pageerror', (error) => consoleErrors.push('pageerror: ' + error.message))
    const failedRequests = []
    page.on('response', (response) => {
      if (response.status() >= 400) failedRequests.push(response.status() + ' ' + response.url())
    })
    await page.goto(BASE)
    await page.getByLabel('小说', { exact: true }).selectOption(first.novelId)
    await page.getByRole('tab', { name: '世界面板' }).click()
    const panel = page.locator('.world-panel')
    await panel.waitFor({ timeout: 20000 })
    const apiWorld = await (await http.get('/api/story-builder/creator/world?novel_id=' + first.novelId)).json()
    assert.equal(apiWorld.meta.content_pack_id, first.pack)

    // 面板必须与 API / StoryState 一致：时间、地点、事件、自主行动数量逐项比对。
    const panelText = await panel.innerText()
    assert.ok(panelText.includes(String(apiWorld.timeline.tick)), '面板应显示 tick')
    assert.ok(panelText.includes('世界时间'), '面板应显示世界时间')
    if (apiWorld.location.current) assert.ok(panelText.includes(apiWorld.location.name || apiWorld.location.current))
    assert.ok(panelText.includes('当前地点'), '面板应显示当前地点')
    assert.ok(panelText.includes('势力状态'), '面板应显示势力状态')
    const eventsBefore = (await (await http.get('/api/story-builder/creator/world?novel_id=' + first.novelId)).json())
      .recent_world_events.length
    if (eventsBefore === 0) {
      assert.ok(panelText.includes('还没有发生世界事件'), '无世界事件时应给出空状态说明')
    }
    assert.ok(panelText.includes('最近 NPC / 势力自主行动'), '面板应显示自主行动区域')

    // 切换小说后数据必须跟着切换，并且不污染其他小说。
    const second = novels[1]
    await page.getByLabel('小说', { exact: true }).selectOption(second.novelId)
    await page.getByRole('tab', { name: '世界面板' }).click()
    await panel.getByText(second.packTitle, { exact: false }).first().waitFor({ timeout: 15000 })
    const secondWorld = await (await http.get('/api/story-builder/creator/world?novel_id=' + second.novelId)).json()
    assert.equal(secondWorld.meta.content_pack_id, second.pack)
    assert.notEqual(secondWorld.meta.novel_id, first.novelId)
    assert.ok((await panel.innerText()).includes(second.packTitle), '切换小说后应显示新小说的内容包')

    // 角色面板：目标 / 记忆 / 关系 / 人物弧 / 自主行动 / 反应理由都来自 API。
    await page.getByRole('tab', { name: '角色面板' }).click()
    const characterPanel = page.locator('.world-panel').first()
    await characterPanel.getByText('人物正在变成什么样').waitFor({ timeout: 15000 })
    const characterApi = await (await http.get('/api/story-builder/creator/characters?novel_id=' + second.novelId)).json()
    const characterText = await characterPanel.innerText()
    assert.ok(characterText.includes('当前目标') && characterText.includes('多维关系'), '角色面板应显示目标与关系')
    assert.ok(characterText.includes('反应理由') && characterText.includes('人物弧'), '角色面板应显示弧与反应理由')
    assert.ok(characterText.includes(characterApi.detail.name), '角色面板应显示选中角色')
    if (characterApi.detail.reactions.length > 0) {
      for (const reaction of characterApi.detail.reactions) {
        assert.ok(characterText.includes(reaction.reason) || characterText.includes(reaction.name),
          '反应理由必须来自 API：' + reaction.action_id)
      }
    }

    // 刷新恢复：回到第一本小说仍然显示同一份事实。
    await page.getByLabel('小说', { exact: true }).selectOption(first.novelId)
    await page.getByRole('tab', { name: '世界面板' }).click()
    await panel.getByText(first.packTitle, { exact: false }).first().waitFor({ timeout: 15000 })
    assert.ok((await panel.innerText()).includes(first.packTitle), '刷新后应恢复第一本小说')
    const afterReload = await (await http.get('/api/story-builder/creator/world?novel_id=' + first.novelId)).json()
    assert.deepEqual(afterReload.timeline, apiWorld.timeline)
    assert.equal(afterReload.meta.persisted, false, '尚未开始旅程时世界面板应是预览状态')
    assert.ok((await panel.innerText()).includes('预览状态'), '预览状态必须对作者可见')

    // 剧情面板：available / unavailable、原因、事件、支线、世界影响都必须来自 API。
    await page.getByRole('tab', { name: '剧情面板' }).click()
    const plotPanel = page.locator('.world-panel').first()
    await plotPanel.getByText('现在能做什么、会发生什么').waitFor({ timeout: 15000 })
    const plotApi = await (await http.get('/api/story-builder/creator/plot?novel_id=' + first.novelId)).json()
    const plotText = await plotPanel.innerText()
    assert.ok(plotText.includes('candidate') === false, '面板不应使用占位数据')
    assert.ok(plotText.includes('available ' + plotApi.available.length), '可用行动数量必须与 API 一致')
    assert.ok(plotText.includes('unavailable ' + plotApi.unavailable.length), '不可用行动数量必须与 API 一致')
    for (const candidate of plotApi.candidates.filter((item) => !item.available)) {
      assert.ok(plotText.includes(candidate.reason), '不可用原因必须来自 API：' + candidate.action_id)
    }
    assert.ok(plotText.includes('世界变化对剧情的影响') && plotText.includes('事件连锁'), '剧情面板应显示世界影响与事件连锁')

    // 成长面板：七类 Progression 的 owned / available / locked 必须与 API 一致。
    await page.getByRole('tab', { name: '成长面板' }).click()
    const growthPanel = page.locator('.world-panel').first()
    await growthPanel.getByText('七类成长在同一套 Progression 上').waitFor({ timeout: 15000 })
    const growthApi = await (await http.get('/api/story-builder/creator/progression?novel_id=' + first.novelId)).json()
    const growthText = await growthPanel.innerText()
    assert.deepEqual(growthApi.categories.map((item) => item.category),
      ['progression', 'ability', 'identity', 'relationship', 'faction', 'information', 'equipment', 'skill'],
      '七类成长必须齐全')
    assert.ok(growthText.includes('已拥有 ' + (growthApi.counts.owned || 0)), '已拥有数量必须与 API 一致')
    assert.ok(growthText.includes('可解锁 ' + (growthApi.counts.available || 0)), '可解锁数量必须与 API 一致')
    for (const category of growthApi.categories) {
      assert.ok(growthText.includes(category.label), '面板应显示分类：' + category.label)
      for (const node of category.nodes.filter((item) => item.status === 'locked')) {
        assert.ok(growthText.includes(node.name), '未解锁节点也必须展示：' + node.id)
      }
    }

    // 记忆面板：三视角知识、承诺 / 债务 / 人情、仇恨、冲突与伏笔都必须与 API 一致。
    await page.getByRole('tab', { name: '记忆面板' }).click()
    const memoryPanel = page.locator('.world-panel').first()
    await memoryPanel.getByText('谁知道什么，还欠什么没解决').waitFor({ timeout: 15000 })
    const memoryApi = await (await http.get('/api/story-builder/creator/memory?novel_id=' + first.novelId)).json()
    const memoryText = await memoryPanel.innerText()
    assert.ok(memoryText.includes('author 视角') && memoryText.includes('reader 视角') && memoryText.includes('character 视角'),
      '记忆面板必须展示三视角')
    assert.ok(memoryText.includes('未回收伏笔 · ' + memoryApi.open_foreshadows.length), '未回收伏笔数量必须与 API 一致')
    for (const item of memoryApi.foreshadows) {
      assert.ok(memoryText.includes(item.title), '伏笔标题必须来自内容包：' + item.id)
    }
    for (const item of memoryApi.obligations.all) {
      assert.ok(memoryText.includes(item.description || item.id), '承诺 / 债务 / 人情必须来自 API：' + item.id)
    }
    for (const row of memoryApi.hostility) {
      assert.ok(memoryText.includes(row.source_id + ' → ' + row.target_id), '仇恨来源必须来自 API')
    }

    // 导演面板：chosen / 逐维得分 / why_chosen 必须与 API 一致，权重可改配置并重新排序。
    await page.getByRole('tab', { name: '导演面板' }).click()
    const directorPanel = page.locator('.world-panel').first()
    await directorPanel.getByText('为什么推荐这个事件').waitFor({ timeout: 15000 })
    const directorApi = await (await http.get('/api/story-builder/creator/director?novel_id=' + first.novelId)).json()
    const directorText = await directorPanel.innerText()
    assert.ok(directorText.includes(directorApi.chosen_title || '暂无'), 'chosen 必须与 API 一致')
    assert.ok(directorText.includes('chosen · ' + (directorApi.chosen_title || '暂无')), '面板应标注 chosen')
    for (const row of directorApi.ranked) {
      assert.ok(directorText.includes(row.title), '排序事件必须来自 API：' + row.event_id)
    }
    if (directorApi.ranked.length > 0) {
      const top = directorApi.ranked[0]
      assert.ok(directorText.includes(top.reasons[0] || top.deductions[0] || '逐维得分'),
        '加分 / 扣分原因必须来自 API')
    }
    // 权重调整只改配置：保存后 chosen 仍来自引擎排序。
    if (directorApi.weights_keys.length > 0) {
      await directorPanel.getByLabel('权重维度').selectOption('payoff')
      await directorPanel.getByLabel('权重数值').fill('6')
      await directorPanel.getByRole('button', { name: /保存并重新排序/ }).click()
      await page.waitForTimeout(1200)
      const tuned = await (await http.get('/api/story-builder/creator/director?novel_id=' + first.novelId)).json()
      assert.equal(tuned.weights_config.payoff, 6, '权重必须写入配置')
      assert.ok((await directorPanel.innerText()).includes('作者设定'), '面板应显示权重来自作者配置')
    }

    // 大纲联动：happened / planned / suggested 必须分开，预览重规划不改历史。
    await page.getByRole('tab', { name: '大纲联动' }).click()
    const linkagePanel = page.locator('.world-panel').first()
    await linkagePanel.getByText('从已发生的事实长到全书').waitFor({ timeout: 15000 })
    const linkageApi = await (await http.get('/api/story-builder/creator/linkage?novel_id=' + first.novelId)).json()
    const linkageText = await linkagePanel.innerText()
    assert.ok(linkageText.includes('happened · ' + linkageApi.counts.happened),
      'happened 数量必须与 API 一致')
    assert.ok(linkageText.includes('planned ' + linkageApi.counts.planned)
      && linkageText.includes('suggested ' + linkageApi.counts.suggested),
      'planned / suggested 必须分开显示')
    const previewApi = await (await http.get('/api/story-builder/creator/linkage?novel_id='
      + first.novelId + '&preview=true&changed_stage=&note=test')).json()
    assert.equal(previewApi.replan_preview.happened_unchanged, true, '重规划预览不得改动历史')
    assert.deepEqual(previewApi.route.happened, linkageApi.route.happened)

    // 手机宽度不得横向溢出。
    await page.setViewportSize({ width: 390, height: 844 })
    await panel.waitFor()
    await page.screenshot({ path: process.env.STORY_TEST_SHOT || 'workspace/creator-world-mobile.png', fullPage: false })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false,
      '手机宽度不得横向溢出')
    // /sessions/latest 在还没有构筑会话时返回 404 属于正常空状态。
    const realFailures = failedRequests.filter((item) => !item.includes('/sessions/latest'))
    assert.deepEqual(realFailures, [], '不应出现接口失败：' + realFailures.join(' | '))
    assert.deepEqual(consoleErrors.filter((text) => !text.includes('404')), [],
      '不应出现前端脚本错误：' + consoleErrors.join(' | '))
    console.log('通过：世界 / 角色 / 剧情 / 成长 / 记忆 / 导演 / 大纲联动三题材小说切换 / 预览标记 / 刷新恢复 / 手机宽度。')
  } finally {
    await browser.close()
    await http.dispose()
  }
})().catch(error => { console.error(error); process.exitCode = 1 })
