// NovelForge V3-P2 Browser Acceptance：World & Character Workspace。
//
// 覆盖：
//   角色 / 世界 有数据与无数据两条路径；
//   实体视觉（EntityVisual 统一 placeholder）、实体点击 → ContextPanel、
//   Esc / 焦点返回、深链接与刷新恢复、唯一 Primary CTA；
//   1440 / 1280 / 1024 / 390 无横向溢出；
//   0 pageerror / 0 requestfailed / 0 未预期 console error / 0 非预期 4xx。
//
// 运行前提（隔离数据根，不接触作者数据）：
//   .venv\Scripts\python.exe scripts/creator_ui_test_server.py --port 8030 --root workspace/v3_ui_test_root
//   node tests/browser_v3_p2_acceptance.cjs   （Playwright 自行安装：npm i -D playwright）
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const BASE = process.env.P2_BASE || 'http://127.0.0.1:8030'
const SHOTS = process.env.P2_SHOTS || 'workspace/product_v3/visual_review/audit'
/** 已推演：角色 / 地点 / 势力都有真实数据。 */
const STARTED = process.env.P2_STARTED || 'novel_v3_accept_783716'
/** 没有构筑会话：走空态路径。 */
const FRESH = process.env.P2_FRESH || 'audit_fmt_55126'
const VIEWPORTS = [[1440, 1000], [1280, 900], [1024, 900], [390, 844]]

;(async () => {
  fs.mkdirSync(SHOTS, { recursive: true })
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const consoleErrors = []
  const pageErrors = []
  const badResponses = []
  const failedRequests = []
  let phase = 'init'
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(`${phase}: ${msg.text()}`)
  })
  page.on('pageerror', (error) => pageErrors.push(`${phase}: ${String(error)}`))
  page.on('requestfailed', (request) => failedRequests.push(
    `${phase}: ${request.method()} ${request.url()}`))
  page.on('response', (response) => {
    if (response.status() >= 400) {
      badResponses.push(`${phase}: ${response.status()} ${response.url().replace(BASE, '')}`)
    }
  })

  const load = async (hash) => {
    await page.goto(`${BASE}/?t=${Date.now()}${hash}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(900)
  }
  const primaryCtaCount = () => page.evaluate(() => {
    const roots = Array.from(document.querySelectorAll(
      '.v3-workspace-view [class*="v3-btn-primary"]'))
    return roots.filter((node) => node.getBoundingClientRect().height > 0).length
  })
  const noOverflow = async (label) => {
    const size = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    assert.ok(size.scrollWidth <= size.clientWidth + 1,
      `${label}: 横向溢出 ${size.scrollWidth} > ${size.clientWidth}`)
  }
  /** 实体点击 → ContextPanel 可访问性 + Esc + 焦点返回。 */
  const expectEntityPanel = async (entitySelector, panelTestId, requireRelations = false) => {
    const target = page.locator(`${entitySelector} .v3-card-hit`).first()
    await target.click()
    await page.getByTestId('v3-context-panel').waitFor({ timeout: 10000 })
    const dialog = await page.evaluate((testId) => {
      const panel = document.querySelector('[data-testid="v3-context-panel"]')
      const labelledby = panel.getAttribute('aria-labelledby')
      return {
        role: panel.getAttribute('role'),
        ariaModal: panel.getAttribute('aria-modal'),
        labelResolves: Boolean(labelledby && document.getElementById(labelledby)),
        focusInside: panel.contains(document.activeElement),
        body: Boolean(document.querySelector(`[data-testid="${testId}"]`)),
        advancedCollapsed: (() => {
          const advanced = document.querySelector('[data-testid="v3-context-advanced"]')
          return advanced ? !advanced.open : true
        })(),
      }
    }, panelTestId)
    assert.equal(dialog.role, 'dialog', `${panelTestId}: 必须是 role="dialog"`)
    assert.equal(dialog.ariaModal, 'true', `${panelTestId}: 必须声明 aria-modal`)
    assert.ok(dialog.labelResolves, `${panelTestId}: aria-labelledby 必须可解析`)
    assert.ok(dialog.focusInside, `${panelTestId}: 打开后焦点必须进入面板`)
    assert.ok(dialog.body, `${panelTestId}: 缺少面向作者的内容区`)
    assert.ok(dialog.advancedCollapsed, `${panelTestId}: Canon/provenance 必须默认折叠`)
    if (requireRelations) {
      // P2 CLOSEOUT：角色面板必须能看到真实关系摘要，或明确的关系空态。
      const relations = await page.evaluate(() => {
        const list = document.querySelector('[data-testid="v3-context-relations"]')
        const empty = document.querySelector('[data-testid="v3-context-relations-empty"]')
        return {
          rows: list ? list.querySelectorAll('li').length : 0,
          empty: Boolean(empty),
        }
      })
      assert.ok(relations.rows > 0 || relations.empty,
        `${panelTestId}: 必须显示关键关系或关系空态`)
    }
    await page.keyboard.press('Escape')
    await page.waitForTimeout(400)
    const after = await page.evaluate((selector) => ({
      open: Boolean(document.querySelector('[data-testid="v3-context-panel"]')),
      restored: Boolean(document.activeElement.closest(selector)),
    }), entitySelector)
    assert.equal(after.open, false, `${panelTestId}: Esc 必须关闭面板`)
    assert.ok(after.restored, `${panelTestId}: 关闭后焦点必须回到实体卡片`)
  }

  try {
    // ------------------------------------------------ 角色：有数据
    phase = 'characters-data'
    await load(`#/n/${STARTED}/characters`)
    await page.getByTestId('v3-characters-block').waitFor({ timeout: 20000 })
    const characters = await page.evaluate(() => ({
      cards: document.querySelectorAll('.v3-character').length,
      visuals: document.querySelectorAll('[data-testid="v3-character-visual"]').length,
      // 视觉不变量（不是历史时点的「必须是占位图」）：
      // 每个实体都有统一视觉容器，且容器状态只能是 image / placeholder 之一；
      // 声明为 image 的必须真的解码成功（不能是坏图或空盒子）。
      badVisuals: Array.from(document.querySelectorAll('[data-testid="v3-character-visual"]'))
        .filter((node) => {
          const state = node.getAttribute('data-artwork')
          if (state !== 'image' && state !== 'placeholder') return true
          const img = node.querySelector('img')
          if (state === 'image' && (!img || !img.complete || img.naturalWidth === 0)) return true
          const box = node.getBoundingClientRect()
          return box.width === 0 || box.height === 0
        }).length,
      protagonistBadge: Array.from(document.querySelectorAll('.v3-character'))
        .some((card) => card.innerText.includes('主角')),
      empty: Boolean(document.querySelector(
        '[data-testid="v3-characters-block"] [data-testid="v3-empty-state"]')),
      heading: (document.querySelector('[data-testid="v3-characters-block"] .v3-section-head')
        || {}).innerText || '',
    }))
    assert.ok(characters.cards > 0, '已推演作品必须列出角色')
    assert.equal(characters.visuals, characters.cards, '每个角色必须有统一视觉容器')
    assert.equal(characters.badVisuals, 0,
      '角色视觉必须是「已解码的图片」或「语义占位」，不能是坏图 / 空盒子')
    assert.ok(characters.protagonistBadge, '主角必须可识别')
    assert.ok(!characters.empty, '有角色时不应显示空态')
    assert.equal(await primaryCtaCount(), 1, '角色工作区只能有一个 Primary CTA')
    await page.screenshot({ path: path.join(SHOTS, 'p2_characters_1440.png'), fullPage: true })
    await expectEntityPanel('.v3-character', 'v3-context-character', true)

    // 刷新 / 深链接恢复
    await page.reload({ waitUntil: 'networkidle' })
    await page.waitForTimeout(800)
    const restored = await page.evaluate(() => ({
      hash: location.hash,
      cards: document.querySelectorAll('.v3-character').length,
    }))
    assert.ok(restored.hash.includes('/characters'), '刷新后必须停在角色工作区')
    assert.equal(restored.cards, characters.cards, '刷新后角色数量必须一致')

    // ------------------------------------------------ 世界：有数据
    phase = 'world-data'
    await load(`#/n/${STARTED}/world`)
    await page.getByTestId('v3-world-locations-block').waitFor({ timeout: 20000 })
    const world = await page.evaluate(() => ({
      locations: document.querySelectorAll('.v3-location').length,
      factions: document.querySelectorAll('.v3-faction').length,
      locationVisuals: document.querySelectorAll(
        '[data-testid="v3-location-visual"]').length,
      factionVisuals: document.querySelectorAll(
        '[data-testid="v3-faction-visual"]').length,
      badVisuals: [
        ...document.querySelectorAll('[data-testid="v3-location-visual"]'),
        ...document.querySelectorAll('[data-testid="v3-faction-visual"]'),
      ].filter((node) => {
        const state = node.getAttribute('data-artwork')
        if (state !== 'image' && state !== 'placeholder') return true
        const img = node.querySelector('img')
        if (state === 'image' && (!img || !img.complete || img.naturalWidth === 0)) return true
        const box = node.getBoundingClientRect()
        return box.width === 0 || box.height === 0
      }).length,
      factionSection: Boolean(document.querySelector('[data-testid="v3-world-factions-block"]')),
    }))
    assert.ok(world.locations > 0, '已推演作品必须列出地点')
    assert.equal(world.locationVisuals, world.locations, '地点必须使用统一视觉容器')
    assert.equal(world.badVisuals, 0,
      '地点 / 势力视觉必须是「已解码的图片」或「语义占位」，不能是坏图 / 空盒子')
    if (world.factions > 0) {
      assert.ok(world.factionSection, '有势力时必须显示势力区块')
      assert.equal(world.factionVisuals, world.factions, '势力必须使用统一视觉容器')
    }
    assert.equal(await primaryCtaCount(), 1, '世界工作区只能有一个 Primary CTA')
    await page.screenshot({ path: path.join(SHOTS, 'p2_world_1440.png'), fullPage: true })
    await expectEntityPanel('.v3-location', 'v3-context-location')
    if (world.factions > 0) {
      await expectEntityPanel('.v3-faction', 'v3-context-faction')
    }

    // ------------------------------------------------ 空态路径
    phase = 'empty-states'
    await load(`#/n/${FRESH}/characters`)
    await page.getByTestId('v3-characters-block').waitFor({ timeout: 20000 })
    const characterEmpty = await page.evaluate(() => {
      const section = document.querySelector('[data-testid="v3-characters-block"]')
      const cta = document.querySelector('[data-testid="v3-character-create"]')
      return {
        empty: Boolean(section && section.querySelector('[data-testid="v3-empty-state"]')),
        title: section && section.querySelector('.v3-empty h3')
          ? section.querySelector('.v3-empty h3').textContent : '',
        ctaVisible: cta ? cta.getBoundingClientRect().bottom <= window.innerHeight : false,
      }
    })
    assert.ok(characterEmpty.empty, '没有角色时必须显示空态')
    assert.equal(characterEmpty.title, '还没有主要角色')
    assert.ok(characterEmpty.ctaVisible, '空态 CTA 必须在首屏可达')
    // 空态时头部不再渲染 CTA，唯一 Primary CTA 由空态承担。
    assert.equal(await primaryCtaCount(), 1, '空态下 Primary CTA 必须唯一（由空态承担）')
    await page.screenshot({ path: path.join(SHOTS, 'p2_characters_empty.png') })

    await load(`#/n/${FRESH}/world`)
    await page.getByTestId('v3-world-locations-block').waitFor({ timeout: 20000 })
    const worldEmpty = await page.evaluate(() => {
      const section = document.querySelector('[data-testid="v3-world-locations-block"]')
      const cta = document.querySelector('[data-testid="v3-world-create"]')
      return {
        empty: Boolean(section && section.querySelector('[data-testid="v3-empty-state"]')),
        factionSection: Boolean(document.querySelector('[data-testid="v3-world-factions-block"]')),
        ctaVisible: cta ? cta.getBoundingClientRect().bottom <= window.innerHeight : false,
      }
    })
    assert.ok(worldEmpty.empty, '没有地点时必须显示空态')
    assert.ok(!worldEmpty.factionSection, '没有势力时不得显示空的势力区块')
    assert.ok(worldEmpty.ctaVisible, '世界空态 CTA 必须在首屏可达')
    await page.screenshot({ path: path.join(SHOTS, 'p2_world_empty.png') })

    // ---------------------------------------------------------- 四视口
    for (const [width, height] of VIEWPORTS) {
      phase = `viewport:${width}`
      await page.setViewportSize({ width, height })
      for (const view of ['characters', 'world']) {
        await load(`#/n/${STARTED}/${view}`)
        await noOverflow(`${view}@${width}`)
        await page.screenshot({ path: path.join(SHOTS, `p2_${view}_${width}.png`) })
      }
    }

    assert.deepEqual(pageErrors, [], `pageerror：${pageErrors.join(' | ')}`)
    assert.deepEqual(failedRequests, [], `requestfailed：${failedRequests.join(' | ')}`)
    assert.deepEqual(consoleErrors, [], `console error：${consoleErrors.join(' | ')}`)
    assert.deepEqual(badResponses, [], `非预期 4xx/5xx：${badResponses.join(' | ')}`)
    console.log('PASS V3-P2 Acceptance：角色（有/无数据）· 世界（有/无数据）· '
      + 'EntityVisual 统一视觉 · 实体点击 ContextPanel（role/Esc/焦点返回/高级详情折叠）· '
      + `唯一 Primary CTA · ${VIEWPORTS.length} 个视口；`
      + '0 pageerror / 0 requestfailed / 0 console error / 0 非预期 4xx')
  } finally {
    await browser.close()
  }
})().catch((error) => {
  console.error(`FAIL ${error.message}`)
  process.exit(1)
})
