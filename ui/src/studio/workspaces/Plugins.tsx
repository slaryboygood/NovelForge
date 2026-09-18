/*
 * 插件页（§50–§52、§108）：只读。
 *
 * 必须诚实表达 trust model：权限控制的是 Host API 能力，不是 OS 安全沙箱。
 * 不提供 enable / disable / 安装 / 配置编辑（V4-09 §65–§67 + 本阶段 §53–§54）。
 */
import type { PluginListDto } from '../../api/studio'
import { Card, Disclosure, SectionHeading } from '../../v3/design-system/primitives'
import Icon from '../../v3/design-system/icons/IconRegistry'
import { StatusBadge, pluginStatusKey } from '../design/status'

const PERMISSION_LABELS: Record<string, string> = {
  'delivery.export': '添加新的交付格式',
  'quality.evaluate': '添加质量检查器',
  'mcp.extend': '添加 MCP 工具或资源',
  'ai.invoke': '使用宿主提供的模型能力',
  'blueprint.read': '读取蓝图内容（只读）',
  'editor.mutate': '修改蓝图内容（需作者批准）',
  'network.request': '使用宿主中介的网络能力',
  'plugin.state': '保存插件自己的状态',
}

const CAPABILITY_LABELS: Record<string, string> = {
  exporter: '交付格式',
  quality_evaluator: '质量检查器',
  mcp_tool: 'MCP 工具',
  mcp_resource: 'MCP 资源',
}

export function Plugins({ data }: { data: PluginListDto }) {
  return (
    <section className="studio-workspace" data-testid="workspace-plugins">
      <SectionHeading icon="locked" title="插件"
        hint="插件可以为 NovelForge 增加能力；本页只读展示状态" />

      <Card tone="elevated" className="studio-trust" testId="plugin-trust-model">
        <header className="studio-tile-head">
          <Icon name="locked" size={20} /><h2>当前插件模型</h2>
          <StatusBadge status={data.trust_model === 'trusted_in_process'
            ? 'compatible' : data.trust_model} />
        </header>
        <p><b>{data.trust_model === 'trusted_in_process'
          ? 'Trusted in-process' : data.trust_model}</b></p>
        <p className="studio-muted">{data.note}</p>
        <p className="studio-muted">
          权限控制的是 NovelForge Host API 能力，不是操作系统安全沙箱；
          本页不提供启用 / 停用 / 安装操作。
        </p>
        <Disclosure summary="权限含义">
          <ul className="studio-kv">
            {(data.permissions.length > 0 ? data.permissions
              : Object.keys(PERMISSION_LABELS)).map((permission) => (
              <li key={permission}>
                <span className="studio-code">{permission}</span>
                <b>{PERMISSION_LABELS[permission] ?? permission}</b>
              </li>
            ))}
          </ul>
        </Disclosure>
      </Card>

      {data.plugins.length === 0 ? (
        <Card tone="quiet" className="studio-empty-card">
          <div className="studio-empty">
            <span className="studio-empty-icon"><Icon name="locked" size={26} /></span>
            <h3>没有已发现的插件</h3>
            <p>{data.hint || '宿主没有发现任何插件（插件需要显式批准后才会执行）。'}</p>
          </div>
        </Card>
      ) : (
        <div className="studio-card-grid">
          {data.plugins.map((plugin) => (
            <Card key={plugin.plugin_id} tone="elevated" as="article"
              className="studio-plugin-card" testId={`plugin-${plugin.plugin_id}`}>
              <header className="studio-card-head">
                <span className="studio-card-icon"><Icon name="locked" size={20} /></span>
                <div className="studio-card-title">
                  <h3>{plugin.name || plugin.plugin_id}</h3>
                  <p className="studio-meta">
                    <span className="studio-code">{plugin.plugin_id}</span>
                    {' · '}v{plugin.version}
                  </p>
                </div>
                <StatusBadge status={pluginStatusKey(plugin)}
                  testId={`plugin-status-${plugin.plugin_id}`} />
              </header>
              {plugin.description ? <p>{plugin.description}</p> : null}
              <ul className="studio-kv">
                <li><span>能力</span><b>{(plugin.capabilities ?? [])
                  .map((row) => CAPABILITY_LABELS[row] ?? row).join('、') || '—'}</b></li>
                <li><span>权限</span><b>{(plugin.permissions ?? [])
                  .map((row) => PERMISSION_LABELS[row] ?? row).join('、') || '—'}</b></li>
                <li><span>批准版本</span><b>{plugin.approved_version || '未批准'}</b></li>
              </ul>
              {plugin.error_code ? (
                <p className="studio-warning-line">
                  <Icon name="warning" size={15} />
                  加载或运行失败（{plugin.error_code}）：{plugin.error_message}
                </p>
              ) : null}
            </Card>
          ))}
        </div>
      )}
    </section>
  )
}
