/*
 * 稳定 backend error code → 作者语言（`docs/v4/V4_UI_CONTRACT.md` §7）。
 *
 * 禁止把 traceback / HTTP 状态码 / Pydantic 错误直接给作者（§58、§92）。
 */

export interface StudioErrorInfo {
  code: string
  message: string
  action?: string
}

export const STUDIO_ERROR_MESSAGES: Record<string, Omit<StudioErrorInfo, 'code'>> = {
  EDITOR_REVISION_CONFLICT: {
    message: '内容已经被更新，请比较最新版本后再保存。', action: '查看最新版本' },
  REVISION_CONFLICT: {
    message: '内容已经被更新，请比较最新版本后再保存。', action: '查看最新版本' },
  EDITOR_PRESERVE_VIOLATION: {
    message: '这次修改碰到了不应改动的字段。', action: '查看受保护字段' },
  EDITOR_NODE_NOT_FOUND: {
    message: '这个节点已经不存在（可能被取代）。', action: '返回列表' },
  BLUEPRINT_NODE_NOT_FOUND: {
    message: '这个节点已经不存在（可能被取代）。', action: '返回列表' },
  EDITOR_VALIDATION_FAILED: { message: '这次修改不符合结构规则，请检查字段内容。' },
  EDITOR_OPERATION_REJECTED: { message: '当前状态不允许这个操作。' },
  EDITOR_OWNERSHIP_MISMATCH: { message: '这本作品不包含该内容。' },
  GENERATION_UNAVAILABLE: {
    message: '当前未配置模型，无法生成。', action: '稍后重试' },
  GENERATION_VALIDATION_FAILED: { message: '生成结果没有通过结构校验，已放弃这次结果。' },
  QUALITY_POLICY_INVALID: { message: '质量策略无效，已回退到默认策略。' },
  REPAIR_PLAN_INVALID: { message: '这次修复计划无效（可能范围重叠）。', action: '重新预览' },
  REPAIR_CONTRACT_CONFLICT: {
    message: '修复与当前内容冲突，需要作者决定。', action: '查看问题' },
  REPAIR_NOT_ALLOWED: { message: '该问题不支持自动修复。', action: '查看问题' },
  REPAIR_ROUND_LIMIT: {
    message: '自动修复达到轮次上限，需要作者决定。', action: '查看问题' },
  DELIVERY_QUALITY_STALE: {
    message: '当前版本还没有最新质量检查。', action: '去检查' },
  DELIVERY_QUALITY_FAILED: { message: '质量检查未通过，暂不能交付。', action: '查看问题' },
  DELIVERY_QUALITY_UNEVALUATED: { message: '还没有做过质量检查。', action: '运行检查' },
  DELIVERY_UNPAID_REQUIRED_SETUP: {
    message: '有必回收的伏笔还没回收。', action: '查看伏笔' },
  DELIVERY_NO_ACCEPTED_REVISION: { message: '还有内容没有被接受。', action: '去接受' },
  DELIVERY_REJECTED_REVISION: { message: '有节点的当前版本被作者拒绝。', action: '查看节点' },
  DELIVERY_MISSING_REQUIRED_NODE: { message: '结构不完整（缺少必需节点）。', action: '查看结构' },
  DELIVERY_REFERENCE_BROKEN: { message: '有引用指向不存在的节点。', action: '查看结构' },
  DELIVERY_ORPHAN_NODE: { message: '有节点没有归属。', action: '查看结构' },
  DELIVERY_PLACEHOLDER_CONTENT: { message: '内容里还有占位文字，不能交付。', action: '查看节点' },
  DELIVERY_INVALIDATION_PENDING: { message: '上游改动还没有复核。', action: '去检查' },
  DELIVERY_FORMAT_UNSUPPORTED: {
    message: '该交付格式不可用（可能对应插件已停用）。', action: '刷新格式列表' },
  DELIVERY_ARTIFACT_EMPTY: { message: '交付物为空，已阻止发布。' },
  DELIVERY_ARTIFACT_MISSING: { message: '交付物缺失，已阻止发布。' },
  DELIVERY_CHECKSUM_MISMATCH: { message: '交付物校验失败，已阻止发布。' },
  DELIVERY_PATH_UNSAFE: { message: '交付物路径不安全，已阻止发布。' },
  DELIVERY_EXPORT_FAILED: { message: '导出未完成，没有发布任何文件。' },
  DELIVERY_SELECTION_INVALID: { message: '这次交付选择不合法，请检查选项。' },
  PLUGIN_PERMISSION_DENIED: {
    message: '插件未获得该权限。', action: '在插件页查看权限' },
  PLUGIN_NOT_APPROVED: { message: '插件尚未被批准。', action: '在插件页查看' },
  PLUGIN_INCOMPATIBLE: { message: '插件与当前版本不兼容。', action: '在插件页查看' },
  PLUGIN_EXECUTION_FAILED: { message: '插件执行失败，已记录（不影响其它功能）。' },
  STUDIO_NOT_FOUND: { message: '找不到这条内容。' },
  STUDIO_VALIDATION_FAILED: { message: '输入不合法，请检查后重试。' },
  STUDIO_CONFLICT: { message: '内容已经变化，请刷新后重试。' },
  STUDIO_OPERATION_FAILED: { message: '操作没有完成，请重试。' },
}

interface ApiErrorLike {
  message?: string
  status?: number
  detail?: unknown
}

function codeFromDetail(detail: unknown): string {
  if (!detail || typeof detail !== 'object') return ''
  const row = detail as Record<string, unknown>
  return String(row.code ?? '')
}

/** 把任意异常映射成作者语言（稳定 code + 建议动作）。 */
export function mapError(reason: unknown): StudioErrorInfo {
  const error = (reason ?? {}) as ApiErrorLike
  const code = codeFromDetail(error.detail) || String(
    (reason as { code?: string })?.code ?? '')
  const known = STUDIO_ERROR_MESSAGES[code]
  if (known) return { code, ...known }
  const raw = String(error.message ?? reason ?? '').trim()
  // 框架内部错误（Pydantic ValidationError / traceback / KeyError）：
  // 只给作者可理解的通用文案，不把内部异常文本透出去（§58、§92）
  if (looksInternal(raw)) {
    return { code: code || 'STUDIO_VALIDATION_FAILED',
      ...STUDIO_ERROR_MESSAGES.STUDIO_VALIDATION_FAILED }
  }
  const cleaned = sanitize(raw)
  return {
    code: code || 'STUDIO_OPERATION_FAILED',
    message: cleaned || STUDIO_ERROR_MESSAGES.STUDIO_OPERATION_FAILED.message,
  }
}

/** 判断是否属于「内部错误文本」（不得原样展示给作者）。 */
export function looksInternal(text: string): boolean {
  const value = String(text || '')
  return /traceback|validation error|field required|value_error|keyerror|typeerror|attributeerror|pydantic|stack trace/i
    .test(value)
}

/** 永不向作者展示：绝对路径 / traceback / 原始 JSON / 内部目录。 */
export function sanitize(text: string): string {
  let out = String(text || '')
  out = out.replace(/[A-Za-z]:\\[^\s"']+/g, '[路径]')
  out = out.replace(/\/[\w.-]+\/[\w./-]+/g, '[路径]')
  out = out.replace(/Traceback[\s\S]*/g, '')
  out = out.replace(/novel\/authoring\S*/g, '[内部路径]')
  if (out.length > 200) out = `${out.slice(0, 200)}…`
  return out.trim()
}

export function isConflict(reason: unknown): boolean {
  const info = mapError(reason)
  return info.code === 'EDITOR_REVISION_CONFLICT' || info.code === 'REVISION_CONFLICT'
    || info.code === 'STUDIO_CONFLICT'
}
