/*
 * 插件页渲染测试（Closure Gate §13）：字段完整 + 诚实 trust model + 只读。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Plugins } from './Plugins'
import type { PluginListDto } from '../../api/studio'

const DATA: PluginListDto = {
  available: true,
  trust_model: 'trusted_in_process',
  note: 'permission 是 Host API capability governance，不是 Python / OS sandbox；'
    + '恶意 in-process 插件仍可直接访问解释器能力',
  permissions: ['delivery.export', 'quality.evaluate', 'mcp.extend', 'plugin.state'],
  read_only: true,
  plugins: [
    { plugin_id: 'com.example.exporter', name: '示例导出插件', version: '1.0.0',
      description: '演示：为交付增加一个文本列表格式',
      capabilities: ['exporter'], permissions: ['delivery.export'],
      status: 'active', approved_version: '1.0.0' },
    { plugin_id: 'com.example.broken', name: '损坏插件', version: '0.9.0',
      capabilities: ['quality_evaluator'], permissions: ['quality.evaluate'],
      status: 'failed', error_code: 'PLUGIN_LOAD_FAILED',
      error_message: '插件模块无法导入（ImportError）' },
  ],
}

describe('Plugin page (§13)', () => {
  it('shows the honest trust model (permission ≠ OS sandbox)', () => {
    render(<Plugins data={DATA} />)
    const trust = screen.getByTestId('plugin-trust-model').textContent || ''
    expect(trust).toContain('Trusted in-process')
    expect(trust).toContain('不是操作系统安全沙箱')
    expect(trust).not.toMatch(/沙箱隔离/)
  })

  it('renders name / id / version / status / capabilities / permissions per plugin', () => {
    render(<Plugins data={DATA} />)
    const card = screen.getByTestId('plugin-com.example.exporter')
    const text = card.textContent || ''
    expect(text).toContain('示例导出插件')
    expect(text).toContain('com.example.exporter')
    expect(text).toContain('v1.0.0')
    expect(text).toContain('交付格式')            // capability 人类文案
    expect(text).toContain('添加新的交付格式')     // permission 人类文案
    expect(screen.getByTestId('plugin-status-com.example.exporter').textContent)
      .toContain('运行中')
  })

  it('surfaces load failures with a stable code instead of hiding them', () => {
    render(<Plugins data={DATA} />)
    const broken = screen.getByTestId('plugin-com.example.broken').textContent || ''
    expect(broken).toContain('PLUGIN_LOAD_FAILED')
    expect(broken).toContain('加载失败')
  })

  it('exposes no operator surface while the boundary is closed', () => {
    render(<Plugins data={DATA} />)
    // 页面只读：没有任何交互控件（enable / disable / install / upload 都不存在）；
    // 文案里出现「本页不提供启用 / 停用 / 安装操作」是**说明**，不是控件。
    expect(document.querySelectorAll('button').length).toBe(0)
    expect(document.querySelectorAll('input, select, textarea').length).toBe(0)
    expect(document.querySelectorAll('[data-testid^="plugin-enable"]').length).toBe(0)
    expect(document.querySelectorAll('[data-testid^="plugin-disable"]').length).toBe(0)
    expect(document.querySelectorAll('[data-testid^="plugin-install"]').length).toBe(0)
    const actions = [...document.querySelectorAll('a')]
      .map((row) => `${row.textContent || ''}${row.getAttribute('href') || ''}`)
      .join(' ')
    expect(actions).not.toMatch(/enable|disable|install|marketplace/i)
  })
})
