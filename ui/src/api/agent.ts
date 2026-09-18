/*
 * Agent Mode HTTP 客户端（V4-11 §97、§103）。
 * UI 只调用 application.services.agent 暴露的 REST facade，不做任何编排判断。
 */
import { requestJson } from '../api'

const BASE = '/api/story-builder/agent'

export interface AgentStepPreview {
  step_id: string
  sequence: number
  action: string
  target: Record<string, unknown>
  mutation: boolean
  requires_approval: boolean
  expected_revision: number | null
  success_criteria: string[]
}

export interface AgentPlanPreviewDto {
  session_id: string
  status: string
  dry_run: boolean
  mutations: number
  plan: {
    plan_id: string
    plan_revision: number
    steps: Record<string, unknown>[]
    estimated_mutations: number
    estimated_model_calls: number
    required_approvals: string[]
    budget_estimate: Record<string, unknown>
  }
  policy: Record<string, unknown>
  snapshot: { digest: string; nodes: number; quality: Record<string, unknown> }
  preview: AgentStepPreview[]
}

export interface AgentStepResultDto {
  step_id: string
  action: string
  status: string
  revision_before: number
  revision_after: number
  changed_nodes: string[]
  error_code: string
  message: string
  warnings: string[]
}

export interface AgentResultDto {
  ok: boolean
  status: string
  session_id: string
  run_id: string
  completed_steps: string[]
  pending_steps: string[]
  changed_nodes: string[]
  new_revisions: Record<string, number>
  quality_summary: Record<string, unknown>
  approvals_required: Record<string, unknown>[]
  pending_approvals?: Record<string, unknown>[]
  usage: Record<string, unknown>
  warnings: string[]
  errors: { code: string; message: string }[]
  stop_reason: string
  needs_human_review: boolean
  steps: AgentStepResultDto[]
  details?: Record<string, unknown>
  semantics?: string
}

export interface AgentStatusDto {
  session: {
    session_id: string
    novel_id: string
    status: string
    goal: Record<string, unknown>
    plan: Record<string, unknown>
    plan_history: Record<string, unknown>[]
    approvals: Record<string, unknown>[]
    decisions: Record<string, unknown>[]
    stop_reason: string
    error_code: string
  }
  runs: Record<string, unknown>[]
  checkpoint: Record<string, unknown>
  pending_approvals: {
    approval_id: string
    step_id: string
    action: string
    target: Record<string, unknown>
    before: Record<string, unknown>
    proposed_after: Record<string, unknown>
    affected_nodes: string[]
    risk: string
    reason: string
    revision_refs: Record<string, number>
  }[]
  audit: Record<string, unknown>[]
}

export const agentApi = {
  plan: (body: {
    novel_id: string
    instruction: string
    scope_kind?: string
    scope_unit_id?: string
    constraints?: string[]
    policy?: Record<string, unknown>
    dry_run?: boolean
  }) => requestJson<AgentPlanPreviewDto>(`${BASE}/plan`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }),
  start: (body: { session_id: string; max_batch_steps?: number }) =>
    requestJson<AgentResultDto>(`${BASE}/start`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  status: (novelId: string, sessionId: string) =>
    requestJson<AgentStatusDto>(
      `${BASE}/${encodeURIComponent(sessionId)}?novel_id=${encodeURIComponent(novelId)}`),
  approve: (sessionId: string, approvalId: string, reason = '') =>
    requestJson<AgentResultDto>(`${BASE}/${encodeURIComponent(sessionId)}/approve`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approval_id: approvalId, reason }),
    }),
  reject: (sessionId: string, approvalId: string, reason = '') =>
    requestJson<AgentResultDto>(`${BASE}/${encodeURIComponent(sessionId)}/reject`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approval_id: approvalId, reason }),
    }),
  resume: (sessionId: string) =>
    requestJson<AgentResultDto>(`${BASE}/${encodeURIComponent(sessionId)}/resume`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    }),
  cancel: (sessionId: string, reason = '') =>
    requestJson<AgentResultDto>(`${BASE}/${encodeURIComponent(sessionId)}/cancel`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, reason }),
    }),
}
