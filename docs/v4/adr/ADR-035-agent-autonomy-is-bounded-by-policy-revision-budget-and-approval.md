# ADR-035 Agent Autonomy Is Bounded By Policy, Revision, Budget And Approval

> 状态：**Accepted**（V4-11 实施完成）　日期：2026-09-18　阶段：V4-11 Agent Mode
> 相关：ADR-017（生成内容是 proposal）、ADR-018（质量是门禁）、ADR-019（repair 受轮次限制）、
> ADR-025（accepted 与 quality-passed 独立）、`docs/v4/V4_AGENT_CONTRACT.md`

## 决策

```text
plan 之前：validate_plan（action allowlist / target / scope / revision / policy / budget）
执行之时：max_steps / max_mutations / batch limit / token·cost·time 预算硬上限
修改之时：expected_revision（不符 → AGENT_REVISION_CONFLICT + step stale + pause）
重大决定：protected action 必须作者批准（accept_revision / deliver / request_accept /
          已接受高层节点重写）
默认：allow_auto_accept = false，allow_delivery = false
```

```text
Quality PASS ≠ Author Accepted：Agent 不得因质量通过而自动接受（除非显式策略 + 批准）
交付：即使目标里写了「大纲做好」也不自动交付；只有明确要求交付 + policy 允许 + 批准
setup_without_payoff 等需要剧情设计的问题：AGENT_NEEDS_HUMAN_REVIEW（不自动含糊修）
```

## 后果

```text
正面：自动化不会降低可控性；预算/轮次/审批都有硬边界；越权与死循环在结构上不可能
负面：作者需要处理 approval 请求；默认策略下"全自动"路径不存在（有意为之）
```
