import { useState } from 'react'
import { api } from './api'
import TruthLayerBadge from './components/TruthLayerBadge'
import { PanelState, useApiData } from './hooks/useApiData'

/** W6-07：设定总览卡（世界 / 主角 / 核心伙伴（狗）/ 势力 / 关系），只读 planned 层。 */
export function SettingOverviewPanel({ novelId }: { novelId: string }) {
  const { data, loading, error } = useApiData(() => api.settingsOverview(novelId), [novelId])
  return <section className="p1-panel" data-testid="overview-panel">
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">设定总览 · W6-07</span>
        <h3>这本小说已经定下来的设定</h3>
      </div>
      <TruthLayerBadge layer="planned" />
    </div>
    <PanelState loading={loading} error={error} empty={!data?.cards.length}
      emptyText="尚未保存设定：先完成引导流的设定步骤。" />
    <div className="p1-card-grid">
      {(data?.cards ?? []).map((card) => <article className="world-card" key={card.card_id}
        data-testid={`overview-card-${card.card_id}`}>
        <div className="world-row-head">
          <h4>{card.title}</h4><span>{card.item_count} 项</span>
        </div>
        {card.note && <p className="world-empty">{card.note}</p>}
        <ul className="p1-list">
          {card.items.map((item) => <li key={item.id}>
            <b>{item.label}{item.core_companion ? ' · 核心伙伴' : ''}</b>
            {item.summary && <span>{item.summary}</span>}
            {item.reason && <small>理由：{item.reason}</small>}
          </li>)}
        </ul>
      </article>)}
    </div>
  </section>
}

/** W6-08：区域与地图卡片；未探索区域保持「未知」。 */
export function RegionCardsPanel({ novelId }: { novelId: string }) {
  const { data, loading, error } = useApiData(() => api.settingsRegions(novelId), [novelId])
  return <section className="p1-panel" data-testid="regions-panel">
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">区域与地图卡 · W6-08</span>
        <h3>已知区域与未知区域分开显示</h3>
      </div>
      <span className="badge">未知 {data?.unknown_count ?? 0} 个</span>
    </div>
    <p className="world-source">当前所在：{data?.current_location || '—'}（与 StoryState 的 location / world 一致）</p>
    <PanelState loading={loading} error={error} empty={!data?.regions.length}
      emptyText="还没有区域数据：内容包需要声明 initial_locations。" />
    <div className="p1-card-grid">
      {(data?.regions ?? []).map((region) => <article className="world-card" key={region.region_id}
        data-testid={`region-card-${region.region_id}`}
        data-explored={region.explored ? 'true' : 'false'}>
        <div className="world-row-head">
          <h4>{region.name}{region.current ? ' · 当前' : ''}</h4>
          <TruthLayerBadge layer={region.truth_layer} />
        </div>
        <dl>
          <div><dt>危险度</dt><dd>{region.danger_label}</dd></div>
          <div><dt>已知资源</dt><dd>{region.known_resources.join('、') || '—'}</dd></div>
          <div><dt>已知信息</dt><dd>{region.known_information.join('、') || '—'}</dd></div>
          <div><dt>进入条件</dt><dd>{region.entry_conditions.join('、') || '—'}</dd></div>
        </dl>
      </article>)}
    </div>
  </section>
}

/** W6-09：人物—势力—伙伴关系网；点击显示数值来源与变更记录。 */
export function RelationshipPanel({ novelId }: { novelId: string }) {
  const [selected, setSelected] = useState('')
  const { data, loading, error } = useApiData(
    () => api.settingsRelationships(novelId, selected), [novelId, selected])
  return <section className="p1-panel" data-testid="relationships-panel">
    <div className="world-panel-head">
      <div>
        <span className="story-builder-kicker">关系网 · W6-09</span>
        <h3>人物 / 势力 / 伙伴之间的关系与来源</h3>
      </div>
      <TruthLayerBadge layer="occurred" />
    </div>
    <div className="p1-node-row" data-testid="relationship-nodes">
      {(data?.nodes ?? []).map((node) => <button type="button" key={node.node_id}
        className={`p1-node ${selected === node.node_id ? 'active' : ''}`}
        onClick={() => setSelected(selected === node.node_id ? '' : node.node_id)}>
        <b>{node.label}</b>
        <small>{node.kind === 'player' ? '主角' : node.kind === 'faction' ? '势力' : '角色'}</small>
      </button>)}
    </div>
    <PanelState loading={loading} error={error} empty={!data?.edges.length}
      emptyText="当前没有关系记录：推演开始后关系会写入 StoryState。" />
    <div className="p1-card-grid">
      {(data?.edges ?? []).map((edge) => <article className="world-card"
        key={`${edge.source}-${edge.target}`}
        data-testid={`relationship-edge-${edge.source}-${edge.target}`}>
        <div className="world-row-head">
          <h4>{edge.source_label} → {edge.target_label}</h4>
          <span>{edge.stage || edge.direction}</span>
        </div>
        <dl>
          {Object.entries(edge.dimensions).map(([key, value]) => <div key={key}>
            <dt>{key}</dt><dd>{value}</dd></div>)}
        </dl>
        {edge.change_records.length > 0 && <details>
          <summary>数值来源与变更记录（{edge.change_records.length}）</summary>
          <ul className="p1-list">
            {edge.change_records.map((row) => <li key={`${row.order}-${row.tick}`}>
              <b>{row.delta >= 0 ? `+${row.delta}` : row.delta}</b>
              <span>{row.reason || row.source}</span>
              <small>tick {row.tick} · order {row.order}</small>
            </li>)}
          </ul>
        </details>}
      </article>)}
    </div>
  </section>
}
