// W2 Edge 实机验收：分支试演 → 结构化对比 → 合并选中成果 → 设为正式路线 → 刷新恢复。
// 只连接隔离测试服务（STORY_TEST_URL），不操作正式作者存档。
const { chromium, request } = require('playwright')
const assert = require('node:assert/strict')

const BASE = process.env.STORY_TEST_URL || 'http://127.0.0.1:8020'
const IDEA = '一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。'

async function startNovel(http, novelId) {
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
}

async function fork(http, novelId, source, label) {
  const response = await http.post('/api/story-builder/runtime/branches/fork?novel_id=' + novelId,
    { data: { source_branch: source, label } })
  assert.equal(response.status(), 200, await response.text())
  return (await response.json()).branch_id
}

async function advance(http, novelId, branch, actionId) {
  const response = await http.post('/api/story-builder/runtime/advance?novel_id=' + novelId,
    { data: { action_id: actionId, branch_id: branch } })
  assert.equal(response.status(), 200, await response.text())
}

;(async () => {
  const http = await request.newContext({ baseURL: BASE })
  const novelId = 'novel_route_' + (Date.now() % 1000000)
  await startNovel(http, novelId)
  const branchA = await fork(http, novelId, 'main', 'A 合作')
  const branchB = await fork(http, novelId, 'main', 'B 拒绝')
  await advance(http, novelId, branchA, 'act_investigate')
  await advance(http, novelId, branchA, 'act_go_hidden')
  await advance(http, novelId, branchB, 'act_go_work')

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
    await page.goto(BASE)
    await page.getByLabel('小说', { exact: true }).selectOption(novelId)
    await page.getByRole('button', { name: '开始构筑' }).click()
    await page.getByRole('tab', { name: '路线实验室' }).waitFor({ timeout: 20000 })
    await page.getByRole('tab', { name: '路线实验室' }).click()
    const panel = page.locator('.route-lab-panel')
    await panel.waitFor({ timeout: 20000 })
    await panel.getByText(/试演 · main/).waitFor({ timeout: 20000 })
    await panel.getByText(branchA, { exact: false }).first().waitFor({ timeout: 20000 })
    await panel.getByText(branchB, { exact: false }).first().waitFor({ timeout: 20000 })
    let text = await panel.innerText()
    assert.ok(text.includes(branchA) && text.includes(branchB), '面板必须列出试演分支')
    assert.ok(text.includes('尚未冻结正式路线'), '一开始不应有正式路线')

    // 从 main 再分一条试演分支，并在面板里执行一次行动。
    await panel.getByRole('button', { name: '从当前分支新建试演分支' }).click()
    await panel.getByText(/已从 main 复制出试演分支/).waitFor({ timeout: 20000 })
    const listed = await (await http.get(
      '/api/story-builder/runtime/branches?novel_id=' + novelId)).json()
    assert.equal(listed.branches.length, 4, '应有三条试演分支 + 主线')

    // 结构化对比：以 main 为基准对比分支 A（A 拿到知识并换了地点）。
    const rowA = panel.locator('.world-row').filter({ hasText: branchA })
    await rowA.getByRole('button', { name: '与当前分支对比' }).click()
    await panel.getByText(/结构化差异/).waitFor({ timeout: 20000 })
    text = await panel.innerText()
    assert.ok(text.includes('knowledge'), '对比必须给出知识差异')
    assert.ok(text.includes('location'), '对比必须给出地点差异')

    // 合并：把 A 的可执行成果合并到 main。
    await panel.getByLabel(`合并来源 ${branchA}`).check()
    await panel.getByRole('button', { name: '预览合并' }).click()
    await panel.getByText(/已列出可合并项与冲突项/).waitFor({ timeout: 20000 })
    const mergePreview = await (await http.post(
      '/api/story-builder/runtime/branches/merge/preview?novel_id=' + novelId,
      { data: { target_branch: 'main', source_branches: [branchA] } })).json()
    assert.ok(mergePreview.sources[0].mergeable.length > 0, 'A 应该有可合并成果')
    await panel.getByRole('button', { name: '执行合并' }).click()
    await panel.getByText(/已合并/).waitFor({ timeout: 20000 })
    const merged = await (await http.get(
      '/api/story-builder/runtime/state?novel_id=' + novelId + '&branch_id=main')).json()
    assert.ok(merged.summary.knowledge.includes('core_record'),
      '合并后 main 必须真的拿到知识：' + JSON.stringify(merged.summary.knowledge))

    // 冻结正式路线（当前试演分支 = 新 fork 出来的那条）。
    await panel.getByRole('button', { name: '把当前分支设为正式路线' }).click()
    await panel.getByText(/已把 .* 设为正式路线/).waitFor({ timeout: 20000 })
    const frozen = await (await http.get(
      '/api/story-builder/runtime/branches?novel_id=' + novelId)).json()
    assert.ok(frozen.official_branch, '必须记录正式路线')
    assert.ok(frozen.frozen_revision >= 0)

    // 刷新恢复：正式路线仍然在，且不依赖前端缓存。
    await page.reload()
    await page.getByLabel('小说', { exact: true }).selectOption(novelId)
    const routeTab = page.getByRole('tab', { name: '路线实验室' })
    if (await routeTab.count() === 0) {
      await page.getByRole('button', { name: '开始构筑' }).click()
    }
    await routeTab.click()
    await page.locator('.route-lab-panel').getByText(/正式路线/).first().waitFor({ timeout: 20000 })

    // 手机宽度不得横向溢出
    await page.setViewportSize({ width: 390, height: 844 })
    await page.locator('.route-lab-panel').waitFor()
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false,
      '手机宽度不得横向溢出')
    console.log('通过：分支试演 / 结构化对比 / 合并 / 正式路线冻结 / 刷新 / 手机宽度。')
  } finally {
    await browser.close()
    await http.dispose()
  }
})().catch(error => { console.error(error); process.exitCode = 1 })
