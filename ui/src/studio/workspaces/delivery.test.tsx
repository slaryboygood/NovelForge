/*
 * Delivery 表单测试（Closure Gate §12）：语义与数据来源，不写死格式。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Delivery } from './Delivery'
import type { DeliveryFormatsDto, DeliveryPreflightDto } from '../../api/studio'

const FORMATS: DeliveryFormatsDto = {
  novel_id: 'alpha',
  format_ids: ['json', 'markdown', 'docx', 'nfpack', 'tlist'],
  formats: [
    { format: 'json', exporter_id: 'delivery.json.v1', version: 1,
      mime_type: 'application/json', extension: 'json', owner_type: 'core',
      owner_id: 'novelforge', text: true },
    { format: 'markdown', exporter_id: 'delivery.markdown.v1', version: 1,
      mime_type: 'text/markdown', extension: 'md', owner_type: 'core',
      owner_id: 'novelforge', text: true },
    { format: 'docx', exporter_id: 'delivery.docx.v1', version: 1,
      mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      extension: 'docx', owner_type: 'core', owner_id: 'novelforge', text: false },
    { format: 'nfpack', exporter_id: 'delivery.nfpack.v1', version: 1,
      mime_type: 'application/zip', extension: 'nfpack', owner_type: 'core',
      owner_id: 'novelforge', text: false },
    { format: 'tlist', exporter_id: 'plugin.com.example.exporter.text-list',
      version: 1, mime_type: 'text/plain', extension: 'tlist',
      owner_type: 'plugin', owner_id: 'com.example.exporter', text: true },
  ],
  profiles: ['reader', 'author', 'machine', 'audit'],
  default_formats: ['json', 'markdown'],
  default_selection_mode: 'accepted',
  read_only: true,
}

function renderDelivery(overrides: Partial<Parameters<typeof Delivery>[0]> = {}) {
  const onDeliver = vi.fn(async () => ({ status: 'delivered' } as DeliveryPreflightDto))
  const utils = render(
    <Delivery novelId="alpha" formats={FORMATS} snapshots={[]} busy=""
      onDeliver={onDeliver} onRefresh={() => {}} {...overrides} />)
  return { ...utils, onDeliver }
}

describe('Delivery form', () => {
  it('defaults to the accepted selection with quality + acceptance requirements', () => {
    renderDelivery()
    const accepted = screen.getByLabelText(/已接受版本/) as HTMLInputElement
    expect(accepted.checked).toBe(true)
    expect((screen.getByLabelText(/要求所有节点都已接受/) as HTMLInputElement).checked)
      .toBe(true)
    expect((screen.getByLabelText(/要求质量检查针对当前版本通过/) as HTMLInputElement)
      .checked).toBe(true)
  })

  it('renders formats from the backend, including plugin exporters', () => {
    renderDelivery()
    for (const format of ['json', 'markdown', 'docx', 'nfpack', 'tlist']) {
      expect(screen.getByTestId(`format-${format}`)).toBeTruthy()
    }
    expect(screen.getByTestId('format-tlist').textContent)
      .toContain('com.example.exporter')
    expect(screen.getByText(/列表来自后端 exporter registry/)).toBeTruthy()
  })

  it('renders a blocked preflight with the author-language reason', async () => {
    const onDeliver = vi.fn(async () => ({
      status: 'blocked',
      validation: {
        ok: false, phase: 'preflight', blocking_reason: '质量结论过期',
        issues: [{ code: 'DELIVERY_QUALITY_STALE', severity: 'blocker',
          message: '当前版本还没有最新质量检查。' }],
      },
      artifacts: [],
    } as DeliveryPreflightDto))
    renderDelivery({ onDeliver })
    fireEvent.click(screen.getByTestId('deliver-submit'))
    await waitFor(() => expect(screen.getByTestId('delivery-result')).toBeTruthy())
    const blocked = screen.getByTestId('delivery-result').textContent || ''
    expect(blocked).toContain('交付被阻止')
    expect(blocked).toContain('当前版本还没有最新质量检查')
    expect(blocked).toContain('DELIVERY_QUALITY_STALE')
    // 被阻止时不提供正式下载
    expect(screen.queryByTestId('download-markdown')).toBeNull()
  })

  it('renders the manifest and download links after a successful delivery', async () => {
    const onDeliver = vi.fn(async () => ({
      status: 'delivered',
      snapshot_id: 'DS_1',
      manifest: { manifest_id: 'M_1', snapshot_id: 'DS_1' },
      artifacts: [
        { format: 'markdown', filename: 'blueprint.md', path: 'exports/blueprint.md',
          size: 5557, checksum: 'abc1234567890', mime_type: 'text/markdown',
          exporter_id: 'delivery.markdown.v1', exporter_version: 1 },
      ],
    } as DeliveryPreflightDto))
    renderDelivery({ onDeliver })
    fireEvent.click(screen.getByTestId('deliver-submit'))
    await waitFor(() => expect(screen.getByTestId('delivery-result')).toBeTruthy())
    const result = screen.getByTestId('delivery-result').textContent || ''
    expect(result).toContain('交付完成')
    expect(result).toContain('DS_1')
    const download = screen.getByTestId('download-markdown')
    expect(download.getAttribute('download')).toBe('blueprint.md')
    expect(download.getAttribute('href'))
      .toBe('/api/story-builder/delivery/DS_1/artifacts/exports/blueprint.md?novel_id=alpha')
  })
})
