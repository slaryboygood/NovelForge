// NovelForge V3 Visual Asset Gate（Visual Asset Contract + P6 Visual Closeout）。
//
// 验证 6 个 required Product Default Artwork **真的在 UI 里渲染**（不是只在 Manifest 里有 URL）：
//
//   A. Novel Landing        无真实封面 → default_novel_cover
//   B. Command Center       无真实 Hero → default_hero_banner
//   C. Character Workspace  无 portrait  → default_character
//   D. World / Location     无地点美术  → default_location
//   E. Faction              无徽记      → default_faction（透明 PNG）
//   F. Outline / Chapter    无章节插画  → default_chapter
//
// 以及：
//   * 页面上 0 broken image（complete && naturalWidth === 0）；
//   * 势力徽记透明通道真的生效（canvas 采样 alpha，不能是黑/白方块）；
//   * 图片不撑破容器、不造成横向溢出、不造成 CLS；
//   * broken asset → semantic icon fallback 回归（拦住图片请求后必须回到图标占位）。
//
// 运行前提（隔离数据根）：
//   .venv\Scripts\python.exe scripts/creator_ui_test_server.py --port 8030 --root workspace/v3_ui_test_root
const { chromium, request } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const BASE = process.env.GATE_BASE || 'http://127.0.0.1:8030'
const SHOTS = process.env.GATE_SHOTS || 'workspace/product_v3/visual_review/audit'
const IDEA = '一个普通维修工发现城市其实运行在一套隐藏的修仙操作系统上。'
const VIEWPORTS = [[1440, 1000], [1280, 900], [1024, 900], [390, 844]]

// `route` 是页面位置：landing = 作品列表，novel = Command Center，其余是工作区。
// `size` 是 docs/V3_VISUAL_ASSET_REQUIREMENTS.json 里声明的尺寸：资源必须真的按规格交付。
const SLOTS = [
  { slot: 'default_novel_cover', route: 'landing', testId: 'v3-novel-cover-', kind: 'novel',
    size: [800, 1200] },
  { slot: 'default_hero_banner', route: 'novel', testId: 'v3-hero-artwork', kind: 'hero',
    size: [1600, 900] },
  { slot: 'default_character', route: 'characters', testId: 'v3-character-visual', kind: 'character',
    size: [800, 1000] },
  { slot: 'default_location', route: 'world', testId: 'v3-location-visual', kind: 'location',
    size: [1200, 675] },
  { slot: 'default_faction', route: 'world', testId: 'v3-faction-visual', kind: 'faction',
    size: [512, 512] },
  { slot: 'default_chapter', route: 'outline', testId: 'v3-chapter-visual', kind: 'chapter',
    size: [960, 540] },
]

let phase = 'init'
const report = (error) => {
  console.error(`FAIL [phase=${phase}] ${error.message}\n${error.stack}`)
  process.exit(1)
}

;(async () => {
  fs.mkdirSync(SHOTS, { recursive: true })
  /*
   * 自带数据准备：这个门禁不依赖开发机上的历史验收作品。
   * 通过 API 现建一本隔离作品（设定 → 起点事实 → 大纲/章节），
   * 这样 fresh product repository 也能直接跑。
   */
  const http = await request.newContext({ baseURL: BASE })
  const NOVEL = `novel_v3_gate_${Date.now() % 1000000}`
  assert.equal((await http.post('/api/story-builder/novels',
    { data: { novel_id: NOVEL, title: NOVEL } })).status(), 201)
  assert.equal((await http.put(`/api/story-builder/creative/brief?novel_id=${NOVEL}`,
    { data: { original_idea: IDEA, selected_genre: 'xianxia', tone: '紧张悬疑' } })).status(), 200)
  const seed = (await (await http.post(
    `/api/story-builder/settings/seed?novel_id=${NOVEL}`, { data: {} })).json()).seed
  assert.equal((await http.put(`/api/story-builder/settings/seed?novel_id=${NOVEL}`,
    { data: { seed, selected: seed.selected } })).status(), 200)
  assert.equal((await http.post(`/api/story-builder/runtime/start?novel_id=${NOVEL}`,
    { data: {} })).status(), 200)
  // 推演几轮：世界实体（角色 / 地点 / 势力）才会真实进入 StoryState。
  for (let index = 0; index < 3; index += 1) {
    const state = await (await http.get(
      `/api/story-builder/runtime/state?novel_id=${NOVEL}`)).json()
    const available = state.candidates.filter((row) => row.available).map((row) => row.action_id)
    if (!available.length) break
    await http.post(`/api/story-builder/runtime/advance?novel_id=${NOVEL}`,
      { data: { action_id: available[index % available.length],
                expected_revision: state.revision } })
  }
  // 章节可视需要真实的章纲链。
  const forge = await http.post(`/api/story-builder/outline/forge?novel_id=${NOVEL}`,
    { data: { branch_id: 'main', volumes: 1, arcs_per_volume: 1, chapters_per_arc: 3 } })
  assert.equal(forge.status(), 200, `大纲锻造失败：${forge.status()}`)

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

  /** 打开某个工作区，并等到页面真的渲染完（含懒加载图片进入视口）。 */
  const load = async (route) => {
    const hash = route === 'landing' ? '#/'
      : route === 'novel' || !route ? `#/n/${NOVEL}` : `#/n/${NOVEL}/${route}`
    await page.goto(`${BASE}/?t=${Date.now()}${hash}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(700)
    await primeLazyImages()
  }
  /**
   * 滚动预热：图片是懒加载的，全页截图前必须让它们真正进入过视口，
   * 否则截图证据里会是一片还没加载的占位（那是截图假象，不是产品缺陷）。
   */
  const primeLazyImages = async () => {
    const height = await page.evaluate(() => document.documentElement.scrollHeight)
    for (let top = 0; top < height; top += 700) {
      await page.evaluate((y) => window.scrollTo(0, y), top)
      await page.waitForTimeout(120)
    }
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.waitForTimeout(400)
  }
  const noOverflow = async (label) => {
    const size = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    assert.ok(size.scrollWidth <= size.clientWidth + 1,
      `${label}: 横向溢出 ${size.scrollWidth} > ${size.clientWidth}`)
  }
  /** broken image = 请求过但解码宽度为 0（会显示浏览器默认裂图图标）。 */
  const brokenImages = () => page.evaluate(() => Array.from(document.images)
    .filter((img) => img.complete && img.naturalWidth === 0)
    .map((img) => img.currentSrc || img.src))
  /** 容器尺寸，用于 CLS 断言：图片就位前后盒子必须一样大。 */
  const boxOf = (selector) => page.locator(selector).first().boundingBox()

  try {
    // --------------------------------------------- 6 个 slot 必须真的渲染图片
    for (const slot of SLOTS) {
      phase = `slot:${slot.slot}`
      await load(slot.route)
      const selector = `[data-testid="${slot.testId}"]`.concat(
        slot.testId.endsWith('-') ? ' img' : ' img')
      const scoped = slot.testId.endsWith('-')
        ? `[data-testid^="${slot.testId}"] img`
        : selector
      const image = page.locator(scoped).first()
      await image.scrollIntoViewIfNeeded()
      await page.waitForFunction((sel) => {
        const node = document.querySelector(sel)
        return Boolean(node && node.complete && node.naturalWidth > 0)
      }, scoped, { timeout: 20000 })
      const info = await page.evaluate((sel) => {
        const img = document.querySelector(sel)
        const wrapper = img.closest('.v3-artwork')
        const box = wrapper.getBoundingClientRect()
        const imageBox = img.getBoundingClientRect()
        return {
          src: img.getAttribute('src'),
          naturalWidth: img.naturalWidth,
          naturalHeight: img.naturalHeight,
          naturalRatio: Math.round((img.naturalWidth / img.naturalHeight) * 1000) / 1000,
          objectFit: getComputedStyle(img).objectFit,
          alt: img.getAttribute('alt'),
          hasLabel: Boolean(wrapper.getAttribute('aria-label')),
          // 作品封面与 Hero 旁边就是真实标题文字，所以它们是装饰性视觉（aria-hidden），
          // 不应该再被读屏重复播报一遍。
          decorative: wrapper.closest('[aria-hidden="true"]') !== null,
          source: wrapper.getAttribute('data-artwork-source'),
          state: wrapper.getAttribute('data-artwork'),
          box: { w: Math.round(box.width), h: Math.round(box.height) },
          overflow: Math.round(Math.max(0, imageBox.right - box.right))
            + Math.round(Math.max(0, imageBox.bottom - box.bottom)),
        }
      }, scoped)
      assert.ok(info.src.includes(slot.slot),
        `${slot.slot}: 必须加载对应默认资源，实际 ${info.src}`)
      assert.ok(info.naturalWidth > 0, `${slot.slot}: 图片必须真的解码成功`)
      assert.deepEqual([info.naturalWidth, info.naturalHeight], slot.size,
        `${slot.slot}: 资源尺寸必须等于 requirements 声明的 ${slot.size.join('x')}，`
        + `实际 ${info.naturalWidth}x${info.naturalHeight}`)
      assert.equal(info.state, 'image', `${slot.slot}: 容器必须处于 image 状态`)
      assert.equal(info.source, 'default',
        `${slot.slot}: 没有真实故事资源时必须回落到产品默认资源`)
      assert.equal(info.alt, '', `${slot.slot}: 语义图片的 alt 由容器 aria-label 承担`)
      assert.equal(info.objectFit, slot.kind === 'faction' ? 'contain' : 'cover',
        `${slot.slot}: object-fit 必须正确（${info.objectFit}）`)
      assert.ok(info.box.w > 0 && info.box.h > 0, `${slot.slot}: 视觉盒子不能塌陷`)
      assert.equal(info.overflow, 0, `${slot.slot}: 图片不得溢出容器`)
      if (slot.kind !== 'faction') {
        if (slot.kind === 'novel' || slot.kind === 'hero') {
          assert.ok(info.decorative,
            `${slot.slot}: 标题已经是文字，封面 / Hero 视觉必须是装饰性的（不得重复播报）`)
        } else {
          assert.ok(info.hasLabel, `${slot.slot}: 图片位必须带可读标签`)
        }
      }
      console.log(`OK   ${slot.slot} ← ${info.src.split('/').pop()} `
        + `(${info.naturalWidth}x${info.naturalHeight}, box ${info.box.w}x${info.box.h})`)
    }

    // ------------------------------------------------ 全页 0 broken image
    phase = 'no-broken-images'
    for (const slot of SLOTS) {
      await load(slot.route)
      const broken = await brokenImages()
      assert.deepEqual(broken, [], `${slot.route}: 不得出现 broken image：${broken}`)
    }

    // -------------------------------- 势力徽记透明通道真的生效（不能是黑白方块）
    phase = 'faction-transparency'
    await load('world')
    const factionAlpha = await page.evaluate(async () => {
      const img = document.querySelector('[data-testid="v3-faction-visual"] img')
      if (!img) return null
      if (!img.complete || !img.naturalWidth) {
        await new Promise((resolve) => { img.onload = resolve })
      }
      const canvas = document.createElement('canvas')
      canvas.width = img.naturalWidth
      canvas.height = img.naturalHeight
      const context = canvas.getContext('2d')
      context.drawImage(img, 0, 0)
      const corners = [
        [0, 0], [img.naturalWidth - 1, 0],
        [0, img.naturalHeight - 1], [img.naturalWidth - 1, img.naturalHeight - 1],
      ]
      const alphas = corners.map(([x, y]) => context.getImageData(x, y, 1, 1).data[3])
      const wrapper = img.closest('.v3-artwork')
      const style = getComputedStyle(wrapper)
      const token = getComputedStyle(document.documentElement)
        .getPropertyValue('--color-bg-elevated').trim()
      return {
        alphas,
        background: style.backgroundColor,
        backgroundImage: style.backgroundImage,
        surfaceToken: token,
      }
    })
    assert.ok(factionAlpha, '势力徽记必须渲染')
    assert.ok(factionAlpha.alphas.every((alpha) => alpha < 255),
      `势力徽记必须是真实透明背景，四角 alpha = ${factionAlpha.alphas}`)
    // 允许「设计系统自己的 Surface」，但绝不允许纯黑 / 纯白方块或棋盘格。
    const hex = factionAlpha.surfaceToken.replace('#', '')
    const tokenRgb = hex.length === 6
      ? `rgb(${parseInt(hex.slice(0, 2), 16)}, ${parseInt(hex.slice(2, 4), 16)}, ` +
        `${parseInt(hex.slice(4, 6), 16)})`
      : ''
    assert.ok(['rgba(0, 0, 0, 0)', 'transparent'].includes(factionAlpha.background)
      || factionAlpha.background === tokenRgb,
    `势力徽记容器只允许透明或设计系统 surface（${tokenRgb}），实际 ${factionAlpha.background}`)
    assert.ok(!['rgb(0, 0, 0)', 'rgb(255, 255, 255)'].includes(factionAlpha.background),
      `势力徽记不得出现黑 / 白方块：${factionAlpha.background}`)
    assert.ok(factionAlpha.backgroundImage === 'none',
      `势力徽记容器不得用渐变 / 棋盘格兜底：${factionAlpha.backgroundImage}`)
    await page.screenshot({ path: path.join(SHOTS, 'gate_faction_1440.png') })

    // ------------------------------------------- 四视口 + 关键页面截图
    for (const [width, height] of VIEWPORTS) {
      phase = `viewport:${width}`
      await page.setViewportSize({ width, height })
      for (const [view, name] of [['landing', 'landing'], ['novel', 'command-center'],
        ['characters', 'characters'], ['world', 'world'],
        ['outline', 'outline'], ['export', 'export']]) {
        await load(view)
        await noOverflow(`${name}@${width}`)
        assert.deepEqual(await brokenImages(), [], `${name}@${width}: 不得有 broken image`)
      }
      await load('novel')
      await page.screenshot({ path: path.join(SHOTS, `gate_command_center_${width}.png`),
        fullPage: true })
      await load('landing')
      await noOverflow(`landing@${width}`)
      await page.screenshot({ path: path.join(SHOTS, `gate_landing_${width}.png`),
        fullPage: true })
    }

    // --------------------------- broken asset → semantic icon fallback 回归
    phase = 'broken-asset-fallback'
    await page.setViewportSize({ width: 1440, height: 1000 })
    const fallbackPage = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    const fallbackConsole = []
    const fallbackPageErrors = []
    fallbackPage.on('console', (msg) => {
      if (msg.type() === 'error') fallbackConsole.push(msg.text())
    })
    fallbackPage.on('pageerror', (error) => fallbackPageErrors.push(String(error)))
    // 故意把所有默认美术请求打断：模拟资源缺失 / CDN 失败。
    await fallbackPage.route('**/assets/default_*', (route) => route.abort())
    await fallbackPage.goto(`${BASE}/#/n/${NOVEL}/characters`, { waitUntil: 'domcontentloaded' })
    await fallbackPage.getByTestId('v3-characters-block').waitFor({ timeout: 30000 })
    await fallbackPage.waitForTimeout(1500)
    const fallback = await fallbackPage.evaluate(() => {
      const wrappers = Array.from(document.querySelectorAll('[data-testid="v3-character-visual"]'))
      return {
        total: wrappers.length,
        placeholders: wrappers.filter((node) => node.getAttribute('data-artwork') === 'placeholder')
          .length,
        withIcon: wrappers.filter((node) => Boolean(node.querySelector('svg'))
          || node.getAttribute('data-artwork') === 'placeholder').length,
        boxes: wrappers.map((node) => {
          const box = node.getBoundingClientRect()
          return { w: Math.round(box.width), h: Math.round(box.height) }
        }),
        broken: Array.from(document.images)
          .filter((img) => img.complete && img.naturalWidth === 0)
          .map((img) => img.currentSrc || img.src),
      }
    })
    assert.ok(fallback.total > 0, '回退回归必须有角色视觉容器')
    assert.equal(fallback.placeholders, fallback.total,
      `图片请求失败时必须全部回到图标占位：${fallback.placeholders}/${fallback.total}`)
    assert.equal(fallback.broken.length, 0,
      `回退后不得留下 broken image：${fallback.broken}`)
    assert.ok(fallback.boxes.every((box) => box.w > 0 && box.h > 0),
      `回退后容器不得塌陷：${JSON.stringify(fallback.boxes)}`)
    assert.ok(fallback.boxes.every((box) => box.w === fallback.boxes[0].w
      && box.h === fallback.boxes[0].h),
    '回退后所有角色视觉容器尺寸必须一致（没有 CLS）')
    assert.deepEqual(fallbackPageErrors, [],
      `回退回归不得有 pageerror：${fallbackPageErrors.join(' | ')}`)
    /*
     * 资源真的请求失败时，浏览器自身会记录一条 resource 加载错误——这条无法也不应该被
     * 前端吞掉（它是真实的网络事实）。这里只允许这一类，其余任何 console error 仍判失败，
     * 从而区分「资源失败 → UI 优雅回退」与「应用自身出错」。
     */
    const appConsoleErrors = fallbackConsole.filter(
      (row) => !/Failed to load resource/.test(row))
    assert.deepEqual(appConsoleErrors, [],
      `回退回归不得有应用级 console error：${appConsoleErrors.join(' | ')}`)
    assert.ok(fallbackConsole.every((row) => /Failed to load resource/.test(row)),
      `回退回归只允许资源加载失败这一类日志：${fallbackConsole.join(' | ')}`)
    await fallbackPage.screenshot({ path: path.join(SHOTS, 'gate_broken_asset_fallback_1440.png') })
    await fallbackPage.close()

    /*
     * 「资源缺失」与「资源失败」是两件事：
     *   * 缺失（Manifest 无 url，例如空态插画）：根本不发请求 → 0 日志、0 失败请求；
     *   * 失败（有 url 但网络/文件坏了）：浏览器会记一条 resource 错误，UI 必须优雅回退。
     * 这里验证缺失路径确实不产生任何请求。
     */
    phase = 'missing-asset-no-request'
    await page.setViewportSize({ width: 1440, height: 1000 })
    await load('landing')
    const emptyArtworkRequests = await page.evaluate(() => Array.from(
      performance.getEntriesByType('resource'))
      .map((row) => row.name)
      .filter((url) => url.includes('empty_')))
    assert.deepEqual(emptyArtworkRequests, [],
      `缺资源的空态插画不得发起请求：${emptyArtworkRequests}`)
    assert.deepEqual(await brokenImages(), [], '空态页不得有 broken image')

    assert.deepEqual(pageErrors, [], `pageerror：${pageErrors.join(' | ')}`)
    assert.deepEqual(failedRequests, [], `requestfailed：${failedRequests.join(' | ')}`)
    assert.deepEqual(consoleErrors, [], `console error：${consoleErrors.join(' | ')}`)
    assert.deepEqual(badResponses, [], `非预期 4xx/5xx：${badResponses.join(' | ')}`)
    console.log('PASS V3 Visual Asset Gate：6/6 required 默认资源真实渲染'
      + '（封面 · Hero · 角色 · 地点 · 势力透明徽记 · 章节）'
      + ' · 0 broken image · broken asset → semantic icon fallback ·'
      + ' 1440/1280/1024/390 · 0 横向溢出 · 0 console error / 0 pageerror /'
      + ' 0 requestfailed / 0 非预期 4xx')
  } finally {
    await browser.close()
  }
})().catch(report)
