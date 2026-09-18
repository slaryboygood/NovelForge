/*
 * 生成任务的父节点解析（V4-10 Completion Gate §3、§4）。
 *
 * 规则（deterministic，不使用 sleep / 不依赖 React 某次 render）：
 *   1. 调用方显式给出 parent_id → 直接用（generation result 是新节点 id 的唯一真相）；
 *   2. 否则基于**刚刚 reload 过的**nodes 解析合法 parent；
 *   3. 恰好 1 个合法 parent → 自动使用；
 *   4. 0 个 → missing（要求先创建父节点，UI 不猜）；
 *   5. ≥2 个 → ambiguous（要求作者显式选择；**不得** latest-wins）；
 *      若作者刚刚创建了其中一个（preferred），把它作为预选项，但仍需显式确认。
 *
 * 父节点类型来自 generation task 契约的 `parent_types`，不在前端发明业务规则。
 */
import type { StudioNode } from '../../api/studio'

export const PARENT_CANDIDATES: Record<string, string[]> = {
  character_arc: ['character'],
  structural_unit: ['story_arc'],
  chapter: ['structural_unit', 'story_arc'],
  scene: ['chapter'],
}

export interface ParentOption {
  nodeId: string
  label: string
  nodeType: string
}

export interface ParentResolution {
  status: 'explicit' | 'root' | 'resolved' | 'missing' | 'ambiguous'
  parentId: string
  options: ParentOption[]
  message: string
}

function labelOf(node: StudioNode): string {
  const data = { ...(node.payload ?? {}), ...(node.visible ?? {}) }
  const title = String(data.title ?? data.name ?? data.premise ?? '').trim()
  return title ? `${title}（${node.node_id}）` : node.node_id
}

/** 合法 parent 候选（顺序稳定：类型顺序 + node_id），便于测试与显示。 */
export function parentOptions(task: string, nodes: StudioNode[]): ParentOption[] {
  const types = PARENT_CANDIDATES[task] ?? []
  if (types.length === 0) return []
  return nodes
    .filter((node) => types.includes(node.node_type))
    .sort((left, right) => {
      const rank = types.indexOf(left.node_type) - types.indexOf(right.node_type)
      return rank !== 0 ? rank : left.node_id.localeCompare(right.node_id)
    })
    .map((node) => ({ nodeId: node.node_id, label: labelOf(node),
      nodeType: node.node_type }))
}

export function resolveParent(task: string, explicitParentId: string,
  nodes: StudioNode[], preferredParentId = ''): ParentResolution {
  const explicit = String(explicitParentId || '').trim()
  if (explicit) {
    return { status: 'explicit', parentId: explicit, options: [],
      message: '' }
  }
  const options = parentOptions(task, nodes)
  if ((PARENT_CANDIDATES[task] ?? []).length === 0) {
    return { status: 'root', parentId: '', options: [], message: '' }
  }
  if (options.length === 0) {
    const wanted = (PARENT_CANDIDATES[task] ?? []).join(' / ')
    return { status: 'missing', parentId: '', options: [],
      message: `还没有可用的上级内容（需要先有 ${wanted}），请先创建后再生成。` }
  }
  if (options.length === 1) {
    return { status: 'resolved', parentId: options[0].nodeId, options,
      message: `将放入：${options[0].label}` }
  }
  const preferred = options.find((row) => row.nodeId === preferredParentId)
  return { status: 'ambiguous', parentId: preferred?.nodeId ?? '', options,
    message: '有多个可选的上级内容，请先选择要放入哪一个。' }
}

export function isAmbiguous(resolution: ParentResolution): boolean {
  return resolution.status === 'ambiguous'
}
