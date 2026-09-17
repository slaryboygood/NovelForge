/**
 * M14：truth-layer 标签（occurred / planned / historical_repair / ui_derived / preview）。
 *
 * UI 必须始终让作者看清「这条信息属于哪一层」，避免把规划误读成已发生事实。
 */
const LABELS: Record<string, { text: string; className: string }> = {
  occurred: { text: '已发生事实', className: 'layer-occurred' },
  planned: { text: '规划 / 设定', className: 'layer-planned' },
  historical_repair: { text: '历史修复（M11/M12 frozen）', className: 'layer-repair' },
  ui_derived: { text: '界面派生（非事实）', className: 'layer-ui' },
  preview: { text: '预览（未提交）', className: 'layer-preview' },
  comparison: { text: '对比视图', className: 'layer-preview' },
}

export default function TruthLayerBadge({ layer }: { layer: string }) {
  const row = LABELS[layer] ?? { text: layer || '未标注', className: 'layer-ui' }
  return <span className={`truth-layer ${row.className}`} data-layer={layer}
    data-testid={`truth-layer-${layer}`}>{row.text}</span>
}
