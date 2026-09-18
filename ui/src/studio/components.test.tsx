/*
 * 组件测试（Closure Gate §7、§10、§11、§16）。
 *
 * 断言的是**语义**（图标 + 文案 + 形状），不是 HTML snapshot。
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { StatusBadge, UI_STATUS_MAP, statusSpec } from './design/status'
import { DiffView, IssueCard, NodeCard, ParentPrompt, ToastStack, useToasts } from './components'
import type { DiffDto, QualityIssueRow, StudioNode } from '../api/studio'

function chapterNode(): StudioNode {
  return { node_id: 'ch_001', node_type: 'chapter', revision: 2, status: 'accepted',
    payload: { title: '维修记录里的异常编号', goal: '确认日志存在' },
    visible: { title: '维修记录里的异常编号', goal: '确认日志存在' }, sequence: 1 }
}

function sceneNode(): StudioNode {
  return { node_id: 'sc_001_01', node_type: 'scene', revision: 3, status: 'proposed',
    parent_id: 'ch_001', sequence: 1,
    payload: { scene_purpose: '让主角拿到第一条证据',
      story_function: ['advance_plot', 'reveal_information'] },
    visible: { scene_purpose: '让主角拿到第一条证据', conflict: '主管拒绝开放记录',
      outcome: '获得线索', story_function: ['advance_plot', 'reveal_information'] } }
}

describe('StatusBadge (UI_STATUS_MAP SSOT)', () => {
  it.each([
    ['accepted', '已接受', 'complete'],
    ['proposed', 'AI 建议', 'creation'],
    ['passed', '检查通过', 'complete'],
    ['failed', '未通过', 'warning'],
    ['blocked', '被阻止', 'warning'],
    ['needs_human_review', '需要作者决定', 'conflict'],
    ['review_rejected', '已评审拒绝', 'close'],
  ])('renders %s with human text + semantic icon', (status, label, icon) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByText(new RegExp(label))).toBeTruthy()
    const svg = document.querySelector(`[data-icon="${icon}"]`)
    expect(svg, `status ${status} 缺少语义图标 ${icon}`).toBeTruthy()
    expect(statusSpec(status).shape).toBeTruthy()   // 形状也是状态信号
  })

  it('keeps PASS and ACCEPT visually distinct (quality ≠ acceptance)', () => {
    expect(UI_STATUS_MAP.passed.label).not.toBe(UI_STATUS_MAP.accepted.label)
    expect(UI_STATUS_MAP.passed.icon).not.toBe('conflict')
    render(<><StatusBadge status="passed" /><StatusBadge status="accepted" /></>)
    expect(screen.getByText(/检查通过/)).toBeTruthy()
    expect(screen.getByText(/已接受/)).toBeTruthy()
  })

  it('shows unknown status verbatim instead of guessing PASS/FAIL', () => {
    render(<StatusBadge status="brand_new_state" />)
    expect(screen.getByText('brand_new_state')).toBeTruthy()
  })
})

describe('Scene Card (Closure Gate §10)', () => {
  it('puts "why this scene exists" on the card front', () => {
    render(<NodeCard node={sceneNode()} />)
    const line = screen.getByTestId('scene-function')
    expect(line.textContent).toContain('这场戏的作用')
    expect(line.textContent).toContain('推进主线')
    expect(line.textContent).toContain('揭示信息')
    // 不是藏在高级字段里：不需要展开任何 disclosure 就能看到
    expect(document.querySelector('details[open]')).toBeNull()
  })

  it('shows status, revision and chapter context', () => {
    render(<NodeCard node={sceneNode()} />)
    expect(screen.getByText(/版本 r3/)).toBeTruthy()
    expect(screen.getAllByText(/场景/).length).toBeGreaterThan(0)
    expect(screen.getByText('AI 建议（待接受）')).toBeTruthy()
  })

  it('renders chapter cards with their own fields', () => {
    render(<NodeCard node={chapterNode()} />)
    expect(screen.getByText('维修记录里的异常编号')).toBeTruthy()
    expect(screen.getByText('已接受')).toBeTruthy()
  })
})

describe('DiffView (Closure Gate §11)', () => {
  const diff: DiffDto = {
    node_id: 'sc_001_01', novel_id: 'alpha', revision_before: 2, revision_after: 3,
    field_changes: [
      { field: 'outcome', kind: 'changed', before: '获得线索', after: '获得线索但失去许可' },
      { field: 'setup', kind: 'changed', before: [], after: ['备用电源曾被破坏'] },
    ],
  }

  it('renders before/after for changed fields (backend diff is the only source)', () => {
    render(<DiffView diff={diff} />)
    expect(screen.getByTestId('diff-outcome').textContent).toContain('修改前')
    expect(screen.getByTestId('diff-outcome').textContent).toContain('获得线索')
    expect(screen.getByTestId('diff-outcome').textContent).toContain('修改后')
    expect(screen.getByTestId('diff-setup').textContent).toContain('备用电源曾被破坏')
  })

  it('renders an explicit no-change state', () => {
    render(<DiffView diff={{ ...diff, field_changes: [] }} />)
    expect(screen.getByTestId('diff-view-empty').textContent).toContain('没有差别')
  })

  it('handles missing diff without inventing one', () => {
    render(<DiffView diff={null} />)
    expect(screen.getByText(/没有可显示的差异/)).toBeTruthy()
  })
})

describe('IssueCard (human language + diagnostic code)', () => {
  const issue: QualityIssueRow = {
    issue_id: 'QI_CANON_1', code: 'CANON_CONTRADICTION', gate: 'Q2',
    severity: 'major', status: 'open', reason: '与既有设定冲突',
    scope: { node_ids: ['sc_001_01'] },
  }

  it('leads with human text and keeps the code as diagnostics', () => {
    render(<IssueCard issue={issue} />)
    expect(screen.getAllByText('与既有设定冲突').length).toBeGreaterThan(0)
    expect(screen.getByText(/诊断码 CANON_CONTRADICTION/)).toBeTruthy()
    expect(screen.getByText('重要')).toBeTruthy()
    expect(screen.getByText(/影响 1 个节点/)).toBeTruthy()
  })
})

describe('Parent prompt (Closure Gate §3.6)', () => {
  it('requires an explicit choice and never auto-confirms', () => {
    const onSelect = vi.fn()
    const onConfirm = vi.fn()
    render(<ParentPrompt open taskLabel="生成场景" message="请选择"
      options={[{ nodeId: 'ch_001', label: '第一章' },
        { nodeId: 'ch_002', label: '第二章' }]}
      selectedId="" onSelect={onSelect} onConfirm={onConfirm} onCancel={() => {}} />)
    fireEvent.click(screen.getByTestId('parent-option-ch_002'))
    expect(onSelect).toHaveBeenCalledWith('ch_002')
    expect(onConfirm).not.toHaveBeenCalled()
  })
})

describe('Toast behaviour (Closure Gate §16)', () => {
  function Harness() {
    const { rows, push, dismiss } = useToasts()
    return (
      <div>
        <button type="button" onClick={() => push('success', '已保存新版本')}>
          触发
        </button>
        <ToastStack rows={rows} onDismiss={dismiss} />
      </div>
    )
  }

  it('appears then auto-dismisses (fake timers, no real waiting)', async () => {
    vi.useFakeTimers()
    try {
      render(<Harness />)
      fireEvent.click(screen.getByText('触发'))
      expect(screen.getByTestId('toast-success').textContent).toContain('已保存新版本')
      await act(async () => {
        vi.advanceTimersByTime(6100)
      })
      expect(screen.queryByTestId('toast-success')).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })
})
