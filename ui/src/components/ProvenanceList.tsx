/**
 * M15：统一的 provenance / lineage 展示（Inspector 记录与 Repair 预览共用）。
 *
 * 只渲染 ref/kind，不做任何业务判断；顺序即后端返回顺序（保持可追溯）。
 */
export interface ProvenanceRow {
  ref: string
  kind: string
}

export default function ProvenanceList({ rows, testId = 'provenance-list' }: {
  rows: ProvenanceRow[]
  testId?: string
}) {
  if (!rows.length) return null
  return <ul className="p1-list provenance-list" data-testid={testId}>
    {rows.map((row) => <li key={`${row.kind}:${row.ref}`}>
      <b>{row.kind}</b><span>{row.ref}</span>
    </li>)}
  </ul>
}
