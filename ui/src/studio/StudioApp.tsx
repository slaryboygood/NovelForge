/*
 * Story Studio 外壳（V4-10 §7、§8、§12、§60–§61、§93–§99）。
 *
 * 路由（hash）→ 数据（每条 panel 独立加载）→ 工作区 → 抽屉 / 通知。
 * UI 只消费 backend 契约；没有本地业务推导。
 */
import {
  Component, useCallback, useEffect, useMemo, useRef, useState, type ErrorInfo,
  type ReactNode,
} from 'react'
import Icon from '../v3/design-system/icons/IconRegistry'
import {
  Button, Card, LoadingState, SectionHeading,
} from '../v3/design-system/primitives'
import {
  studioApi, type DeliveryFormatsDto, type DeliverySnapshotRow, type PluginListDto,
  type QualityCenterDto, type StudioNode, type StudioOverview,
} from '../api/studio'
import { mapError } from './design/errors'
import { resolveParent, type ParentOption } from './design/parents'
import { StatusBadge } from './design/status'
import { nodeTypeLabel } from './design/fields'
import { OperationPanel, ParentPrompt, ToastStack, useToasts } from './components'
import { NodeDrawer } from './NodeDrawer'
import { Overview } from './workspaces/Overview'
import { NodeWorkspace } from './workspaces/NodeWorkspace'
import { Quality } from './workspaces/Quality'
import { Delivery } from './workspaces/Delivery'
import { Plugins } from './workspaces/Plugins'
import { Agent } from './workspaces/Agent'
import { STUDIO_NAV, parseStudioRoute, studioHash, type StudioRoute,
  type StudioView } from './nav'
import './studio.css'

/* ------------------------------------------------------------ error boundary */

class StudioBoundary extends Component<{ name: string; children: ReactNode },
  { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 只记录开发者信息，不向作者展示（§92）
    console.error('[studio] panel failed', this.props.name, error, info)
  }

  render() {
    if (this.state.failed) {
      return (
        <Card tone="quiet" className="studio-empty-card">
          <div className="studio-empty">
            <span className="studio-empty-icon"><Icon name="warning" size={24} /></span>
            <h3>这一块暂时出了问题</h3>
            <p>Story Studio 的其它部分仍然可用。可以切换到别的页面，或稍后重试。</p>
            <Button variant="secondary" onClick={() => this.setState({ failed: false })}>
              重新尝试
            </Button>
          </div>
        </Card>
      )
    }
    return this.props.children
  }
}

/* ------------------------------------------------------------------- hook */

function useAsync<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const reload = useCallback(async (): Promise<T | null> => {
    setLoading(true)
    setError('')
    let payload: T | null = null
    try {
      payload = await loader()
      setData(payload)
    } catch (reason) {
      payload = null
      setError(mapError(reason).message)
    } finally {
      setLoading(false)
    }
    return payload
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { void reload() }, [reload])
  return { data, loading, error, reload, setData }
}

/* ------------------------------------------------------------------ shell */

export default function StudioApp() {
  const [route, setRoute] = useState<StudioRoute>(() => parseStudioRoute(window.location.hash))
  const [drawerNode, setDrawerNode] = useState('')
  const [busy, setBusy] = useState('')
  const [operation, setOperation] = useState<{ open: boolean; label: string }>(
    { open: false, label: '' })
  const { rows: toasts, push, dismiss } = useToasts()

  useEffect(() => {
    const onHash = () => setRoute(parseStudioRoute(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    if (route.name === 'studio' && route.entityId
      && ['characters', 'story', 'scenes'].includes(route.view)) {
      setDrawerNode(route.entityId)
    }
  }, [route])

  const go = useCallback((novelId: string, view: StudioView, entityId = '') => {
    const hash = studioHash(novelId, view, entityId)
    if (window.location.hash === hash) setRoute(parseStudioRoute(hash))
    else window.location.hash = hash
  }, [])

  if (route.name === 'v3') return <V3Redirect />
  if (route.name === 'legacy') return <LegacyRedirect query={route.query} />

  if (route.name === 'landing' || !route.novelId) {
    return <StudioLanding onOpen={(novelId) => go(novelId, 'overview')}
      notify={push} />
  }

  return (
    <StudioShell
      novelId={route.novelId} view={route.view} drawerNode={drawerNode}
      setDrawerNode={setDrawerNode} go={go} busy={busy} setBusy={setBusy}
      toasts={toasts} notify={push} dismiss={dismiss}
      setOperation={(label) => setOperation({ open: Boolean(label), label })}
      operation={operation} onCloseOperation={() => setOperation({ open: false, label: '' })} />
  )
}

function V3Redirect() {
  useEffect(() => { window.location.href = `${window.location.pathname}?ui=v3#/` }, [])
  return <LoadingState label="正在打开旧版工作台…" />
}

function LegacyRedirect({ query }: { query: string }) {
  useEffect(() => {
    window.location.href = `${window.location.pathname}?ui=v2${query ? `#${query}` : '#/story-builder'}`
  }, [query])
  return <LoadingState label="正在打开高级工具…" />
}

/* ---------------------------------------------------------------- landing */

function StudioLanding({ onOpen, notify }: {
  onOpen: (novelId: string) => void
  notify: (tone: 'success' | 'warning' | 'error' | 'info', message: string) => void
}) {
  const novels = useAsync(() => studioApi.novels(), [])
  const [novelId, setNovelId] = useState('')
  const [title, setTitle] = useState('')
  const [creating, setCreating] = useState(false)

  return (
    <div className="studio-landing" data-testid="studio-landing">
      <header className="studio-landing-head">
        <div>
          <p className="studio-eyebrow">NovelForge</p>
          <h1>Story Studio</h1>
          <p className="studio-hero-sub">
            选一本作品继续，或者从一句前提开始新的故事。
          </p>
        </div>
        <span className="studio-landing-actions">
          <a className="studio-link" href="?ui=v2#/story-builder">高级工具（旧版）</a>
        </span>
      </header>

      <Card tone="elevated" className="studio-create-card">
        <SectionHeading icon="creation" title="新建作品"
          hint="作品编号用于目录与深链接，创建后不可修改" />
        <div className="studio-create-row">
          <label className="studio-field">
            <span>作品编号</span>
            <input type="text" value={novelId} placeholder="例如：my_novel"
              onChange={(event) => setNovelId(event.target.value)} data-testid="novel-id" />
          </label>
          <label className="studio-field">
            <span>作品名（可选）</span>
            <input type="text" value={title} placeholder="例如：阿尔法计划"
              onChange={(event) => setTitle(event.target.value)} data-testid="novel-title" />
          </label>
          <Button variant="primary" icon="add" disabled={creating || novelId.trim().length < 3}
            testId="create-novel"
            onClick={async () => {
              setCreating(true)
              try {
                await studioApi.createNovel({ novel_id: novelId.trim(),
                  title: title.trim() || novelId.trim() })
                notify('success', '作品已创建')
                onOpen(novelId.trim())
              } catch (reason) {
                notify('error', mapError(reason).message)
              } finally {
                setCreating(false)
              }
            }}>
            {creating ? '创建中…' : '创建并开始'}
          </Button>
        </div>
      </Card>

      <section className="studio-workspace">
        <h2 className="studio-h2">我的作品</h2>
        {novels.loading ? <LoadingState /> : null}
        {novels.error ? <p className="studio-error-inline">{novels.error}</p> : null}
        {novels.data && novels.data.novels.length === 0 ? (
          <Card tone="quiet" className="studio-empty-card">
            <div className="studio-empty">
              <span className="studio-empty-icon"><Icon name="creation" size={26} /></span>
              <h3>还没有作品</h3>
              <p>作品是这一切的起点：先建一本，然后从故事前提开始。</p>
            </div>
          </Card>
        ) : null}
        <div className="studio-card-grid">
          {(novels.data?.novels ?? []).map((novel) => (
            <Card key={novel.novel_id} tone="elevated" as="article"
              onClick={() => onOpen(novel.novel_id)}
              testId={`novel-card-${novel.novel_id}`} className="studio-novel-card">
              <header className="studio-card-head">
                <span className="studio-card-icon"><Icon name="book" size={22} /></span>
                <div className="studio-card-title">
                  <h3>{novel.title || novel.novel_id}</h3>
                  <p className="studio-meta">{novel.genre || '未设置题材'}</p>
                </div>
              </header>
              <p className="studio-meta">
                {novel.cast ?? 0} 位人物 · {novel.factions ?? 0} 个势力
              </p>
            </Card>
          ))}
        </div>
      </section>
    </div>
  )
}

/* ----------------------------------------------------------------- shell */

function StudioShell({ novelId, view, drawerNode, setDrawerNode, go, busy, setBusy,
  toasts, notify, dismiss, operation, setOperation, onCloseOperation }: {
  novelId: string
  view: StudioView
  drawerNode: string
  setDrawerNode: (nodeId: string) => void
  go: (novelId: string, view: StudioView, entityId?: string) => void
  busy: string
  setBusy: (value: string) => void
  toasts: ReturnType<typeof useToasts>['rows']
  notify: ReturnType<typeof useToasts>['push']
  dismiss: (id: string) => void
  operation: { open: boolean; label: string }
  setOperation: (label: string) => void
  onCloseOperation: () => void
}) {
  const overview = useAsync(() => studioApi.overview(novelId), [novelId])
  const nodes = useAsync(() => studioApi.blueprint(novelId), [novelId])
  /** 最近一次生成结果里的新节点（§4：generation result = 新节点 id 的真相）。 */
  const lastCreated = useRef<{ nodeType: string; nodeId: string }>(
    { nodeType: '', nodeId: '' })
  const [parentPrompt, setParentPrompt] = useState<{
    open: boolean
    task: string
    taskLabel: string
    message: string
    options: ParentOption[]
    selectedId: string
  }>({ open: false, task: '', taskLabel: '', message: '', options: [],
    selectedId: '' })
  const quality = useAsync(
    () => (view === 'quality' ? studioApi.quality(novelId) : Promise.resolve(null)),
    [novelId, view])
  const formats = useAsync(
    () => (view === 'delivery' ? studioApi.deliveryFormats(novelId)
      : Promise.resolve(null)), [novelId, view])
  const snapshots = useAsync(
    () => (view === 'delivery' ? studioApi.deliverySnapshots(novelId)
      : Promise.resolve(null)), [novelId, view])
  const plugins = useAsync(
    () => (view === 'plugins' ? studioApi.plugins() : Promise.resolve(null)), [view])

  const blueprintNodes: StudioNode[] = nodes.data?.nodes ?? []
  const nodesOf = (types: string[]) => blueprintNodes.filter(
    (row) => types.includes(row.node_type))

  const reloadAll = useCallback(() => {
    void overview.reload()
    void nodes.reload()
    if (view === 'quality') void quality.reload()
    if (view === 'delivery') { void formats.reload(); void snapshots.reload() }
    if (view === 'plugins') void plugins.reload()
  }, [overview, nodes, quality, formats, snapshots, plugins, view])

  const generate = useCallback(async (task: string, parentId = '', nodeType = '') => {
    // 父节点解析（Completion Gate §3/§4，完全 deterministic）：
    //   显式 parent → 直接用；否则**先 reload**再解析（不使用任何本地缓存候选）：
    //   唯一候选自动 → 0 个报缺 → 多个要求作者显式选择（绝不 latest-wins）。
    let resolution
    if (String(parentId || '').trim()) {
      resolution = resolveParent(task, parentId, [])
    } else {
      const fresh = await nodes.reload()
      const freshNodes = (fresh?.nodes ?? []) as StudioNode[]
      resolution = resolveParent(task, '', freshNodes, lastCreated.current.nodeId)
    }
    if (resolution.status === 'missing') {
      notify('warning', resolution.message)
      return
    }
    if (resolution.status === 'ambiguous') {
      setParentPrompt({ open: true, task, taskLabel: TASK_LABELS[task] ?? '生成',
        message: resolution.message, options: resolution.options,
        selectedId: resolution.parentId })
      return
    }
    const resolvedParent = resolution.parentId
    setBusy(task)
    setOperation(TASK_LABELS[task] ?? '生成中')
    try {
      const result = await studioApi.generate({ novel_id: novelId, task,
        parent_id: resolvedParent, node_type: nodeType })
      notify('success', `${TASK_LABELS[task] ?? '生成'}完成：这是 AI 建议，等待你接受`)
      // 生成结果是新节点 id 的唯一真相（§4）：交给下一次父节点解析优先使用
      if (result?.node?.node_id) {
        lastCreated.current = { nodeType: result.node.node_type,
          nodeId: result.node.node_id }
      }
      reloadAll()
    } catch (reason) {
      notify('error', mapError(reason).message)
    } finally {
      setBusy('')
      onCloseOperation()
    }
  }, [novelId, blueprintNodes, nodes, notify, reloadAll, setBusy, setOperation,
    onCloseOperation])

  const status = overview.data
  const setupWarn = (status?.setup?.unpaid_required ?? 0) > 0
  const blockers = status?.quality?.open_blockers ?? 0

  const main = useMemo(() => {
    switch (view) {
      case 'overview':
        return status ? (
          <Overview data={status}
            onNavigate={(target) => go(novelId, (target || 'creation') as StudioView)}
            onGenerate={(task) => void generate(task)}
            generating={busy} />
        ) : <LoadingState label="正在读取作品状态…" />
      case 'creation':
        return (
          <NodeWorkspace title="创造" icon="creation"
            hint="最高层的故事意图：前提 / 主题 / 核心冲突"
            nodes={nodesOf(['premise', 'theme'])}
            nodeTypes={['premise', 'theme']}
            generateActions={[{ task: 'premise', label: '生成故事前提' },
              { task: 'theme', label: '生成主题' }]}
            generating={busy} onGenerate={(task) => void generate(task)}
            onOpen={(nodeId) => setDrawerNode(nodeId)} testId="workspace-creation" />
        )
      case 'world':
        return (
          <NodeWorkspace title="世界" icon="world"
            hint="规则 / 地点 / 势力 / 资源：AI 建议与 Canon 约束要分清"
            nodes={nodesOf(['world'])} nodeTypes={['world']}
            generateActions={[{ task: 'world', label: '生成世界设定' }]}
            generating={busy} onGenerate={(task) => void generate(task)}
            onOpen={(nodeId) => setDrawerNode(nodeId)} testId="workspace-world" />
        )
      case 'characters':
        return (
          <NodeWorkspace title="人物" icon="character"
            hint="人物卡与人物弧：目标 → 压力 → 危机 → 选择 → 终点"
            nodes={nodesOf(['character', 'character_arc'])}
            nodeTypes={['character', 'character_arc']}
            generateActions={[{ task: 'character', label: '生成人物' }]}
            generating={busy} onGenerate={(task) => void generate(task)}
            onOpen={(nodeId) => setDrawerNode(nodeId)} testId="workspace-characters" />
        )
      case 'story':
        return (
          <NodeWorkspace title="故事" icon="story"
            hint="故事弧 → 结构单元 → 章节（结构由数据决定，不写死三幕）"
            nodes={nodesOf(['story_arc', 'structural_unit', 'chapter'])}
            nodeTypes={['story_arc', 'structural_unit', 'chapter']}
            generateActions={[{ task: 'story_arc', label: '生成故事弧' },
              { task: 'structural_unit', label: '生成结构单元' },
              { task: 'chapter', label: '生成章节', needsParent: true }]}
            generating={busy} onGenerate={(task) => void generate(task)}
            onOpen={(nodeId) => setDrawerNode(nodeId)} testId="workspace-story" />
        )
      case 'scenes':
        return (
          <NodeWorkspace title="场景" icon="simulation"
            hint="每场戏存在的理由（故事功能）写在卡片正面"
            nodes={nodesOf(['scene'])} nodeTypes={['scene']} groupByParent
            generateActions={[{ task: 'scene', label: '生成场景', needsParent: true }]}
            generating={busy} onGenerate={(task) => void generate(task)}
            onOpen={(nodeId) => setDrawerNode(nodeId)} testId="workspace-scenes" />
        )
      case 'quality':
        return quality.data ? (
          <Quality data={quality.data as QualityCenterDto}
            busy={busy}
            onOpenNode={(nodeId) => setDrawerNode(nodeId)}
            onEvaluate={async () => {
              setBusy('evaluate')
              try {
                await studioApi.evaluateQuality({ novel_id: novelId })
                notify('success', '质量检查完成')
                void quality.reload()
                void overview.reload()
              } catch (reason) {
                notify('error', mapError(reason).message)
              } finally { setBusy('') }
            }}
            onPlan={async (issueIds) => {
              setBusy('plan')
              try {
                return await studioApi.planRepair({ novel_id: novelId,
                  issue_ids: issueIds })
              } catch (reason) {
                notify('error', mapError(reason).message)
                return { status: 'failed' }
              } finally { setBusy('') }
            }}
            onRepair={async (issueIds) => {
              setBusy('repair')
              try {
                const outcome = await studioApi.executeRepair({ novel_id: novelId,
                  issue_ids: issueIds })
                notify('success', '修复完成，正在复核')
                void nodes.reload()
                void quality.reload()
                return outcome
              } catch (reason) {
                notify('error', mapError(reason).message)
                return { status: 'failed' }
              } finally { setBusy('') }
            }}
            onVerify={async (issueIds) => {
              try {
                const verification = await studioApi.verifyRepair({ novel_id: novelId,
                  issue_ids: issueIds })
                if (verification.needs_human_review
                  || verification.status === 'needs_human_review') {
                  notify('warning', '需要作者决定（不是修复失败）')
                }
                void quality.reload()
                void overview.reload()
                return verification
              } catch (reason) {
                notify('error', mapError(reason).message)
                return { status: 'unresolved' }
              }
            }} />
        ) : <LoadingState label="正在读取质量结论…" />
      case 'delivery':
        return (
          <Delivery novelId={novelId}
            formats={formats.data as DeliveryFormatsDto | null}
            snapshots={(snapshots.data?.snapshots ?? []) as DeliverySnapshotRow[]}
            busy={busy}
            onRefresh={reloadAll}
            onDeliver={async (body) => {
              setBusy('deliver')
              try {
                const result = await studioApi.deliver({ novel_id: novelId, ...body })
                notify(result.status === 'delivered' ? 'success' : 'warning',
                  result.status === 'delivered' ? '交付完成' : '交付被阻止')
                void snapshots.reload()
                void overview.reload()
                return result
              } catch (reason) {
                notify('error', mapError(reason).message)
                throw reason
              } finally { setBusy('') }
            }} />
        )
      case 'plugins':
        return plugins.data ? <Plugins data={plugins.data as PluginListDto} />
          : <LoadingState label="正在读取插件状态…" />
      case 'agent':
        return (
          <Agent novelId={novelId} notify={notify}
            onOpenNode={(nodeId) => setDrawerNode(nodeId)} />
        )
      case 'settings':
        return (
          <section className="studio-workspace">
            <SectionHeading icon="settings" title="项目设置"
              hint="作品元数据（由既有作品 API 提供；本阶段只读展示）" />
            <Card tone="elevated">
              <ul className="studio-kv">
                <li><span>作品编号</span><b>{novelId}</b></li>
                <li><span>作品名</span><b>{status?.title ?? novelId}</b></li>
                <li><span>题材</span><b>{status?.genre || '未设置'}</b></li>
                <li><span>蓝图节点</span><b>{status?.blueprint.node_count ?? 0}</b></li>
              </ul>
            </Card>
          </section>
        )
      default:
        return <LoadingState />
    }
  }, [view, status, busy, novelId, blueprintNodes, nodes, quality, formats, snapshots,
    plugins, generate, go, notify, reloadAll, setBusy, setDrawerNode])

  return (
    <div className="studio-root" data-testid="studio-shell">
      <header className="studio-topbar">
        <a className="studio-brand" href="#/studio" data-testid="studio-brand">
          <Icon name="book" size={18} /><span>Story Studio</span>
        </a>
        <div className="studio-topbar-status">
          <span className="studio-topbar-title" data-testid="topbar-title">
            {status?.title ?? novelId}
          </span>
          <StatusBadge status={status?.quality.status ?? 'unevaluated'}
            testId="topbar-quality" />
          {setupWarn ? (
            <span className="studio-topbar-warn" data-testid="topbar-setup-warning">
              <Icon name="warning" size={15} />
              {status?.setup.unpaid_required} 条伏笔未回收
            </span>
          ) : null}
          {blockers > 0 ? (
            <span className="studio-topbar-warn" data-testid="topbar-blockers">
              <Icon name="warning" size={15} />{blockers} 个门禁被阻止
            </span>
          ) : null}
          <span className="studio-meta">
            {overview.loading ? '同步中…' : '已同步'}
          </span>
        </div>
        <div className="studio-topbar-actions">
          <Button variant="ghost" size="sm" icon="review"
            onClick={() => go(novelId, 'quality')}>检查</Button>
          <Button variant="secondary" size="sm" icon="export"
            onClick={() => go(novelId, 'delivery')}>交付</Button>
        </div>
      </header>

      <div className="studio-body">
        <nav className="studio-nav" aria-label="Story Studio 导航">
          {STUDIO_NAV.map((item) => (
            <button key={item.view} type="button"
              className={`studio-nav-item ${view === item.view ? 'is-active' : ''}`}
              aria-current={view === item.view ? 'page' : undefined}
              onClick={() => go(novelId, item.view)}
              data-testid={`nav-${item.view}`}>
              <Icon name={item.icon} size={20} />
              <span className="studio-nav-label">{item.label}</span>
              <span className="studio-nav-hint">{item.hint}</span>
            </button>
          ))}
          <a className="studio-nav-item studio-nav-extra"
            href={`?ui=v2#/story-builder?novel_id=${encodeURIComponent(novelId)}`}>
            <Icon name="settings" size={18} />
            <span className="studio-nav-label">高级工具</span>
            <span className="studio-nav-hint">旧版面板（兼容）</span>
          </a>
        </nav>

        <main className="studio-main">
          {overview.error ? (
            <p className="studio-error-inline" role="alert">{overview.error}</p>
          ) : null}
          {view !== 'overview' && nodes.error ? (
            <p className="studio-error-inline" role="alert">{nodes.error}</p>
          ) : null}
          <StudioBoundary name={view}>
            {main}
          </StudioBoundary>
        </main>
      </div>

      <NodeDrawer open={Boolean(drawerNode)} novelId={novelId} nodeId={drawerNode}
        onClose={() => setDrawerNode('')}
        onChanged={(message) => { notify('success', message); reloadAll() }}
        notify={notify} />

      <ParentPrompt open={parentPrompt.open} taskLabel={parentPrompt.taskLabel}
        message={parentPrompt.message} options={parentPrompt.options}
        selectedId={parentPrompt.selectedId}
        onSelect={(nodeId) => setParentPrompt({ ...parentPrompt, selectedId: nodeId })}
        onCancel={() => setParentPrompt({ ...parentPrompt, open: false })}
        onConfirm={() => {
          const chosen = parentPrompt.selectedId
          const task = parentPrompt.task
          setParentPrompt({ ...parentPrompt, open: false })
          void generate(task, chosen)
        }} />

      <OperationPanel open={operation.open} label={operation.label}
        onClose={onCloseOperation} />
      <ToastStack rows={toasts} onDismiss={dismiss} />
    </div>
  )
}

const TASK_LABELS: Record<string, string> = {
  premise: '生成故事前提',
  theme: '生成主题',
  world: '生成世界设定',
  character: '生成人物',
  character_arc: '生成人物弧',
  story_arc: '生成故事弧',
  structural_unit: '生成结构单元',
  chapter: '生成章节',
  scene: '生成场景',
}

export { nodeTypeLabel }
