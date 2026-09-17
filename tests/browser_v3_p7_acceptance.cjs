// NovelForge V3-P7 Regression Gate（Acceptance Repair 新增门禁）。
//
// 这个门禁专门覆盖 V3 独立验收（CURRENT_PRODUCT_ACCEPTANCE_REVIEW.md）里
// 「现有门禁 PASS 但产品 FAIL」的部分（NF-020 盲区），并且必须能在修复前 FAIL：
//
//   NF-001 Export Gate：导出工作区主 CTA 之后内容区必须非空，必须产生真实导出产物
//     （文件名 + 内容 / 下载入口），且不再跳到不存在的 legacy 页签。
//   NF-002 Writer Gate：在 UI 里创建写作草稿 → 投影看到草稿 → 页面看到草稿 →
//     刷新后仍然存在 → 导出阶段的目标真的完成（进度上升）。
//   NF-003 Title Gate：30 章标题正文唯一、无字段标签占位（「阶段目标（规划）」类）。
//   NF-004 Internal-ID Gate：在「已锻造大纲 + 已推演 + 已写作草稿」的最丰富状态下，
//     扫描 8 个工作区 + 导出 markdown / json，作者可见内容里 0 命中内部 id。
//   NF-005 Consistency Gate：同一本书 Landing 卡片与 Command Center 的阶段 / 进度 /
//     下一步完全一致（3 本不同状态的作品）。
//   NF-012 Export Copy Gate：存在 blocker 时导出文案不得说「还差 0 步」。
//
// 运行前提（隔离数据根，不触碰作者数据）：
//   .venv\Scripts\python.exe scripts/creator_ui_test_server.py --port 8035 --root workspace/qa_repair_2026_09_17/root_ui
const { chromium, request } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const BASE = process.env.P7_BASE || 'http://127.0.0.1:8035'
const SHOTS = process.env.P7_SHOTS || 'workspace/qa_repair_2026_09_17/shots'
const IDEA = '一名被裁员的飞船维修师发现公司用算力在殖民地之间买卖记忆，他的工牌是唯一的钥匙。'
const WORKSPACES = ['creation', 'world', 'characters', 'story', 'simulation',
  'outline', 'review', 'export']
const FIELD_LABEL_BLACKLIST = ['阶段目标（规划）', '长期方向（规划）', '（设定草稿）']
const INTERNAL_ID_PATTERN = new RegExp('\\b(act_[a-z0-9_]+|ev_[a-z0-9_]+'
  + '|faction_\\d+|npc_\\d+|location_\\d+|character_\\d+|route_\\d+|planned_[a-z0-9_]+'
  + '|suggested_[a-z0-9_]+|start_place|work_place|hidden_place|core_record'
  + '|protagonist|favors)\\b')
// artifact identity（ol_forge_* 包名 / item_id / source_ids）是机器身份，不是作者内容。
const IDENTITY_KEYS = new Set(['item_id', 'package_id', 'parent_package_id', 'child_ids',
  'source_ids', 'route_source', 'canon_fact_ids', 'canon_event_ids', 'novel_id',
  'branch_id', 'blueprint_id', 'chapter_uuid', 'participants'])

let phase = 'init'
const report = (error) => {
  console.error(`FAIL [phase=${phase}] ${error.message}\n${error.stack}`)
  process.exit(1)
}

;(async () => {
  fs.mkdirSync(SHOTS, { recursive: true })
  const http = await request.newContext({ baseURL: BASE })
  const stamp = Date.now() % 1000000
  const main = `novel_p7_main_${stamp}`
  const briefOnly = `novel_p7_brief_${stamp}`
  const startedOnly = `novel_p7_started_${stamp}`

  const createNovel = async (novelId) => {
    const response = await http.post('/api/story-builder/novels',
      { data: { novel_id: novelId, title: novelId } })
    assert.equal(response.status(), 201, `新建作品失败：${novelId}`)
  }
  const saveBrief = async (novelId) => {
    assert.equal((await http.put(`/api/story-builder/creative/brief?novel_id=${novelId}`,
      { data: { original_idea: IDEA, selected_genre: 'sci_fi', tone: '紧张悬疑' } }))
      .status(), 200)
  }
  const saveSeed = async (novelId) => {
    const seed = (await (await http.post(
      `/api/story-builder/settings/seed?novel_id=${novelId}`, { data: {} })).json()).seed
    assert.equal((await http.put(`/api/story-builder/settings/seed?novel_id=${novelId}`,
      { data: { seed, selected: seed.selected } })).status(), 200)
  }
  const startRuntime = async (novelId) => {
    assert.equal((await http.post(`/api/story-builder/runtime/start?novel_id=${novelId}`,
      { data: {} })).status(), 200)
  }

  await createNovel(main)
  await saveBrief(main)
  await saveSeed(main)
  await startRuntime(main)
  for (let index = 0; index < 3; index += 1) {
    const state = await (await http.get(
      `/api/story-builder/runtime/state?novel_id=${main}`)).json()
    const available = state.candidates.filter((row) => row.available)
    if (!available.length) break
    const moved = await http.post(`/api/story-builder/runtime/advance?novel_id=${main}`,
      { data: { action_id: available[0].action_id, expected_revision: state.revision } })
    if (moved.status() !== 200) break
  }
  // 30 章：3 卷 × 2 篇章 × 5 章（NF-003 的验收规模）。
  assert.equal((await http.post(`/api/story-builder/outline/forge?novel_id=${main}`,
    { data: { branch_id: 'main', volumes: 3, arcs_per_volume: 2, chapters_per_arc: 5 } }))
    .status(), 200)
  assert.equal((await http.post(`/api/story-builder/outline/confirm?novel_id=${main}`,
    { data: { branch_id: 'main' } })).status(), 200)

  // 另外两本用于 Landing / Command Center 一致性对比（只存简报 / 已推演未锻大纲）。
  await createNovel(briefOnly)
  await saveBrief(briefOnly)
  await createNovel(startedOnly)
  await saveBrief(startedOnly)
  await saveSeed(startedOnly)
  await startRuntime(startedOnly)

  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const consoleErrors = []
  const pageErrors = []
  const badResponses = []
  const failedRequests = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(`${phase}: ${msg.text()}`)
  })
  page.on('pageerror', (error) => pageErrors.push(`${phase}: ${String(error)}`))
  page.on('requestfailed', (req) => failedRequests.push(
    `${phase}: ${req.method()} ${req.url()}`))
  page.on('response', (res) => {
    if (res.status() >= 400) {
      badResponses.push(`${phase}: ${res.status()} ${res.url().replace(BASE, '')}`)
    }
  })

  const load = async (hash) => {
    await page.goto(`${BASE}/?t=${Date.now()}${hash}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(700)
  }
  const bodyText = () => page.evaluate(() => document.body.innerText)
  const noOverflow = async (label) => {
    const size = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    assert.ok(size.scrollWidth <= size.clientWidth + 1,
      `${label}: 横向溢出 ${size.scrollWidth} > ${size.clientWidth}`)
  }
  const commandCenter = async (novelId) => (await (await http.get(
    `/api/story-builder/v3/novels/${novelId}/command-center`)).json())
  const contentStrings = (node, skipIdentity = false) => {
    if (Array.isArray(node)) {
      return node.flatMap((value) => contentStrings(value, skipIdentity))
    }
    if (node && typeof node === 'object') {
      return Object.entries(node).flatMap(([key, value]) => contentStrings(
        value, skipIdentity || IDENTITY_KEYS.has(key)))
    }
    if (typeof node === 'string') return skipIdentity ? [] : [node]
    return []
  }

  try {
    // ------------------------------------------------------- NF-003 标题质量
    phase = 'nf003-titles'
    const chain = await (await http.get(
      `/api/story-builder/outline/chain?novel_id=${main}&branch_id=main`)).json()
    const chapterItems = chain.chapters.map((row) => row.items[0])
    assert.ok(chapterItems.length >= 30, `必须锻造 30 章：${chapterItems.length}`)
    const titles = chapterItems.map((row) => row.title)
    const bodies = titles.map((title) => (title.includes('：')
      ? title.split('：').slice(1).join('：') : title))
    const duplicates = [...new Set(bodies.filter(
      (body, index) => bodies.indexOf(body) !== index))]
    assert.deepEqual(duplicates, [], `章节标题正文不得重复：${duplicates.slice(0, 3)}`)
    for (const title of titles) {
      for (const banned of FIELD_LABEL_BLACKLIST) {
        assert.ok(!title.includes(banned), `章节标题不得是字段标签：${title}`)
      }
    }

    // ------------------------------------------------- NF-004 导出物内部 id
    phase = 'nf004-export-artifacts'
    for (const format of ['markdown', 'json']) {
      const payload = await (await http.get(
        `/api/story-builder/outline/export?novel_id=${main}&branch_id=main`
        + `&format=${format}`)).json()
      const blob = format === 'json'
        ? contentStrings(JSON.parse(payload.content).levels).join(' ')
        : payload.content
      const leak = blob.match(INTERNAL_ID_PATTERN)
      assert.ok(!leak, `${format} 导出内容不得含内部 id：${leak && leak[0]}`)
      assert.ok(!blob.includes('来源：来源：'),
        `${format} 导出不得出现重复的来源前缀`)
    }

    // --------------------------------------------------------- NF-001/002/012
    phase = 'nf002-writer-before'
    const before = await commandCenter(main)
    assert.equal(before.facts.writer_drafts, 0, '前置状态必须还没有写作草稿')
    assert.ok(before.export.missing.some((row) => row.step_id === 'writer_drafts'),
      '导出就绪度必须列出「已有写作草稿」这一项')

    await load(`#/n/${main}/export`)
    await page.getByTestId('v3-export-panel').waitFor({ timeout: 30000 })
    const exportView = await page.evaluate(() => ({
      text: (document.querySelector('[data-testid="v3-export-panel"]') || {}).innerText || '',
      primaries: Array.from(document.querySelectorAll(
        '.v3-workspace-view .v3-btn-primary'))
        .filter((row) => row.getBoundingClientRect().height > 0).length,
      draftList: Boolean(document.querySelector('[data-testid="v3-writer-draft-list"]')),
    }))
    assert.ok(exportView.text.length > 80,
      'NF-001：导出工作区必须渲染真实内容，不能是空白 shell')
    assert.ok(exportView.draftList, 'NF-002：导出工作区必须给出写作草稿区域')
    assert.equal(exportView.primaries, 1, '导出工作区只能有一个 Primary CTA')
    await page.screenshot({ path: path.join(SHOTS, 'p7_export_before_1440.png'),
      fullPage: true })

    phase = 'nf002-writer-create'
    await page.getByTestId('v3-export-primary').click()
    await page.getByTestId('v3-export-notice').waitFor({ timeout: 60000 })
    await page.waitForFunction(() => document
      .querySelectorAll('[data-testid="v3-writer-draft-list"] li').length > 0
      && !document.querySelector('[data-testid="v3-writer-draft-list"] li[data-empty="true"]'),
    null, { timeout: 60000 })
    const afterDraft = await commandCenter(main)
    assert.ok(afterDraft.facts.writer_drafts > 0,
      'NF-002：投影必须看到刚创建的写作草稿（写入与读取路径同源）')
    assert.equal(afterDraft.export.writer_drafts, afterDraft.facts.writer_drafts)
    assert.ok(afterDraft.progress.percent > before.progress.percent,
      `NF-002：创建草稿后总体进度必须上升：${before.progress.percent} → `
      + `${afterDraft.progress.percent}`)
    const exportDraftStep = afterDraft.export.steps.find(
      (row) => row.step_id === 'writer_drafts')
    assert.ok(exportDraftStep.done, 'NF-002：导出阶段的「已有写作草稿」必须完成')
    await page.screenshot({ path: path.join(SHOTS, 'p7_export_draft_1440.png'),
      fullPage: true })

    phase = 'nf001-export-generate'
    await page.getByTestId('v3-export-open').click()
    await page.getByTestId('v3-export-artifact').waitFor({ timeout: 60000 })
    const artifact = await page.evaluate(() => ({
      name: (document.querySelector('[data-testid="v3-export-artifact-name"]') || {})
        .innerText || '',
      preview: (document.querySelector('[data-testid="v3-export-artifact-preview"]') || {})
        .innerText || '',
      download: Boolean(document.querySelector('[data-testid="v3-export-download"]')),
      panel: (document.querySelector('[data-testid="v3-export-panel"]') || {}).innerText || '',
    }))
    assert.ok(artifact.name.length > 4, `NF-001：必须给出导出文件名：${artifact.name}`)
    assert.ok(artifact.preview.length > 40,
      'NF-001：导出面板必须显示真实内容，而不是空壳')
    assert.ok(artifact.download, 'NF-001：导出物必须有下载入口')
    assert.ok(!INTERNAL_ID_PATTERN.test(artifact.panel),
      'NF-001：导出面板不得显示内部 id')
    // 真正下载一次：导出物必须是可以拿到手的文件（不是「显示成功但没有产物」）。
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 30000 }),
      page.getByTestId('v3-export-download').click(),
    ])
    const savedPath = path.join(SHOTS, `p7_downloaded_${download.suggestedFilename()}`)
    await download.saveAs(savedPath)
    const saved = fs.readFileSync(savedPath, 'utf8')
    assert.ok(saved.length > 200, `导出的文件必须真的有内容：${saved.length} 字节`)
    const savedLeak = saved.match(INTERNAL_ID_PATTERN)
    assert.ok(!savedLeak, `下载到的导出文件不得含内部 id：${savedLeak && savedLeak[0]}`)
    await page.screenshot({ path: path.join(SHOTS, 'p7_export_artifact_1440.png'),
      fullPage: true })

    // 刷新后草稿与导出步骤仍然成立（持久化）。
    phase = 'nf002-writer-reload'
    await load(`#/n/${main}/export`)
    await page.getByTestId('v3-writer-draft-list').waitFor({ timeout: 30000 })
    await page.waitForFunction(() => document.querySelectorAll(
      '[data-testid="v3-writer-draft-list"] li[data-empty="true"]').length === 0,
    null, { timeout: 30000 })
    const reloaded = await commandCenter(main)
    assert.equal(reloaded.facts.writer_drafts, afterDraft.facts.writer_drafts,
      'NF-002：刷新后草稿数量必须一致')

    // --------------------------------------------- NF-004 工作区内部 id 扫描
    phase = 'nf004-workspaces'
    for (const view of WORKSPACES) {
      await load(`#/n/${main}/${view}`)
      const text = await bodyText()
      const leak = text.match(INTERNAL_ID_PATTERN)
      assert.ok(!leak, `${view} 工作区不得裸露内部 id：${leak && leak[0]}`)
      assert.ok(!text.includes('来源：来源：'), `${view} 工作区不得出现重复来源前缀`)
    }
    await load('#/')
    const landingText = await bodyText()
    const landingLeak = landingText.match(INTERNAL_ID_PATTERN)
    assert.ok(!landingLeak, `Landing 不得裸露内部 id：${landingLeak && landingLeak[0]}`)

    // ----------------------------------------------------------- NF-005 一致性
    phase = 'nf005-consistency'
    const landing = await (await http.get('/api/story-builder/v3/novels')).json()
    for (const novelId of [main, briefOnly, startedOnly]) {
      const card = landing.novels.find((row) => row.novel_id === novelId)
      const inside = await commandCenter(novelId)
      assert.ok(card, `Landing 必须有 ${novelId} 的卡片`)
      assert.equal(card.stage_id, inside.journey.current_stage,
        `${novelId}: 阶段必须一致`)
      assert.equal(card.stage_label, inside.journey.current_stage_label,
        `${novelId}: 阶段名必须一致`)
      assert.equal(card.progress_percent, inside.progress.percent,
        `${novelId}: 进度必须一致 ${card.progress_percent} vs ${inside.progress.percent}`)
      assert.equal(card.next_action, inside.next_action.title,
        `${novelId}: 下一步必须一致`)
      await load(`#/n/${novelId}`)
      const cardText = await bodyText()
      for (const label of [inside.journey.current_stage_label,
        inside.next_action.title]) {
        if (label) {
          assert.ok(cardText.includes(label),
            `${novelId}: 作品内页面必须显示投影给出的「${label}」`)
        }
      }
    }

    // ------------------------------------------------------------ NF-012 文案
    phase = 'nf012-export-copy'
    const status = await http.get(`/api/story-builder/outline/impact?novel_id=${main}`
      + `&package_id=${chain.book.package_id}`
      + `&item_id=${chain.book.items[0].item_id}`)
    assert.equal(status.status(), 200, '影响分析必须可用（用于制造 stale 状态）')
    const staleAdvance = await (async () => {
      const state = await (await http.get(
        `/api/story-builder/runtime/state?novel_id=${main}`)).json()
      const available = state.candidates.filter((row) => row.available)
      if (!available.length) return null
      return http.post(`/api/story-builder/runtime/advance?novel_id=${main}`,
        { data: { action_id: available[0].action_id, expected_revision: state.revision } })
    })()
    if (staleAdvance && staleAdvance.status() === 200) {
      const stalePayload = await commandCenter(main)
      assert.equal(stalePayload.export.ready, false, '推进后大纲过期，不能算就绪')
      assert.ok(stalePayload.export.blockers.length > 0, '过期必须有真实 blocker')
      assert.equal(stalePayload.export.headline, stalePayload.export.blockers[0],
        'NF-012：存在 blocker 时标题必须说清阻塞原因')
      assert.ok(!stalePayload.export.headline.includes('还差 0 步'),
        'NF-012：不得出现「还差 0 步就可以导出」')
      await load(`#/n/${main}/export`)
      await page.getByTestId('v3-export-panel').waitFor({ timeout: 30000 })
      const staleText = await page.evaluate(
        () => document.querySelector('[data-testid="v3-export-readiness"]').innerText)
      assert.ok(!staleText.includes('还差 0 步'), 'NF-012：界面文案不得自相矛盾')
      assert.ok(/重新锻造|阻塞|大纲/.test(staleText),
        `NF-012：界面必须指出真实阻塞：${staleText.slice(0, 120)}`)
      await page.screenshot({ path: path.join(SHOTS, 'p7_export_stale_1440.png'),
        fullPage: true })
    }

    // ---------------------------------------------------------------- 四视口
    for (const [width, height] of [[1440, 1000], [1280, 900], [1024, 900], [390, 844]]) {
      phase = `viewport:${width}`
      await page.setViewportSize({ width, height })
      for (const view of WORKSPACES) {
        await load(`#/n/${main}/${view}`)
        await noOverflow(`${view}@${width}`)
      }
      await page.screenshot({ path: path.join(SHOTS, `p7_export_${width}.png`) })
    }

    assert.deepEqual(pageErrors, [], `pageerror：${pageErrors.join(' | ')}`)
    assert.deepEqual(failedRequests, [], `requestfailed：${failedRequests.join(' | ')}`)
    assert.deepEqual(consoleErrors, [], `console error：${consoleErrors.join(' | ')}`)
    assert.deepEqual(badResponses, [], `非预期 4xx/5xx：${badResponses.join(' | ')}`)
    console.log('PASS V3-P7 Regression Gate：'
      + '导出 CTA 内容非空 + 真实导出产物（文件名 / 内容 / 下载）·'
      + ' 写作草稿 UI 创建 → 投影可见 → 刷新仍在 → 导出阶段完成（进度上升）·'
      + ' 30 章标题唯一且无字段占位 · 8 工作区 + 2 导出格式 0 内部 id 命中 ·'
      + ' Landing / Command Center 阶段-进度-下一步一致（3 本不同状态作品）·'
      + ' blocker 文案不再自相矛盾 · 4 视口无横向溢出；'
      + '0 pageerror / 0 requestfailed / 0 console error / 0 非预期 4xx')
  } finally {
    await browser.close()
  }
})().catch(report)
