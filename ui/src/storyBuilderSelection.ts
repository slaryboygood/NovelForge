/*
 * 设定候选的共享选择语义（V2 面板与 V3 创作工作区共用一份，避免两套规则）。
 *
 * 这是展示层规则：哪些组可以多选、组的中文标签。
 * 结构、id 与合法性始终由引擎决定。
 */

export const SETTING_GROUP_LABELS: Record<string, string> = {
  world_rules: '世界规则',
  protagonist: '主角',
  characters: '重要角色',
  factions: '势力',
  relationships: '初始关系网',
  progression: '成长体系',
  conflicts: '核心矛盾',
  main_line: '主线方向',
  foreshadows: '初始伏笔',
}

export const SETTING_GROUP_ORDER: string[] = Object.keys(SETTING_GROUP_LABELS)

export const MULTIPLE_SELECTION_GROUPS = new Set([
  'characters', 'factions', 'relationships', 'foreshadows', 'progression',
  'world_rules',
])

export function isMultipleSelectionGroup(group: string): boolean {
  return MULTIPLE_SELECTION_GROUPS.has(group)
}

/** 单选组选中新项 / 多选组切换：返回该组新的选中 id 列表。 */
export function toggleSelection(group: string, current: string[], id: string): string[] {
  if (current.includes(id)) return current.filter((item) => item !== id)
  return isMultipleSelectionGroup(group) ? [...current, id] : [id]
}
