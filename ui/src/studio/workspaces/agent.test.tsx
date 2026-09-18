/* Agent 面板组件测试（V4-11 §109）：goal input → plan preview → 审批入口。 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Agent } from './Agent'

vi.mock('../../api/studio', () => ({
  studioApi: {
    blueprint: vi.fn(async () => ({ nodes: [] })),
  },
}))

vi.mock('../../api/agent', () => ({
  agentApi: {
    plan: vi.fn(async () => ({
      session_id: 'session_1', status: 'planning', dry_run: true, mutations: 0,
      plan: { plan_id: 'plan_1', plan_revision: 1, steps: [], estimated_mutations: 1,
        estimated_model_calls: 1, required_approvals: [], budget_estimate: {} },
      policy: {}, snapshot: { digest: 'd', nodes: 1, quality: {} },
      preview: [
        { step_id: 's1', sequence: 1, action: 'inspect_blueprint',
          target: { kind: 'novel' }, mutation: false, requires_approval: false,
          expected_revision: null, success_criteria: [] },
        { step_id: 's2', sequence: 2, action: 'accept_revision',
          target: { kind: 'node', node_id: 'ch_001' }, mutation: true,
          requires_approval: true, expected_revision: 3, success_criteria: [] },
      ],
    })),
    start: vi.fn(), status: vi.fn(), approve: vi.fn(), reject: vi.fn(),
    resume: vi.fn(), cancel: vi.fn(),
  },
}))

describe('Agent workspace', () => {
  it('shows goal input and structured plan preview (not a chat box)', async () => {
    render(<Agent novelId="alpha" onOpenNode={() => {}} notify={() => {}} />)
    expect(screen.getByTestId('agent-goal-input')).toBeTruthy()
    fireEvent.change(screen.getByTestId('agent-goal-input'),
      { target: { value: '把第一幕扩展到 3 个章节' } })
    fireEvent.click(screen.getByTestId('agent-plan'))
    await waitFor(() => expect(screen.getByTestId('agent-plan-preview')).toBeTruthy())
    expect(screen.getByTestId('agent-steps').textContent).toContain('查看当前状态')
    expect(screen.getByTestId('agent-steps').textContent).toContain('需要你确认')
    expect(screen.getByTestId('agent-start')).toBeTruthy()
  })
})
