---
name: novelforge-v4.0.2.workflows.prepare-final-delivery
description: 端到端流程：交付前检查（accepted + 质量）→ 预检 → 建立交付 → 校验 manifest → 下载。
---

# prepare-final-delivery

- **Skill ID**: `novelforge-v4.0.2.workflows.prepare-final-delivery`
- **Version**: 1（baseline `V4.0.2`；继承 V4.0.1 同名 workflow）
- **Capability Module**: `workflows`（组合层）
- **Product owner**: 无

## Purpose

把"我要交付"变成一条可审计路径：**先满足条件，再发布，最后能验证**。

## Use when

- 准备对外交付 / 存档。
- 交付被拒时需要定位差什么。

## Do not use when

- 质量还没修 → 先 `review-and-repair-blueprint`。

## Preconditions

```text
Blueprint 内容基本完成；作者已决定接受哪些节点
```

## Required inputs

| 输入 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `novel_id` | 是 | — | 目标作品 |
| `formats` | 否 | `["json","markdown"]` | 可含 `docx` / `nfpack` |
| `profile` | 否 | `author` | reader / author / machine / audit |

## Authoritative interfaces

```text
见各步骤 skill（本 workflow 不新增接口）
```

## Procedure（只引用 skill ID）

```text
Step 1 novelforge-v4.0.1.quality.evaluate-blueprint        → 交付前评估（Q9）
Step 2 novelforge-v4.0.1.quality.inspect-quality-report    → 确认无 blocker
Step 3 novelforge-v4.0.1.studio.inspect-overview           → 看 accepted / proposed 计数
Step 4 novelforge-v4.0.1.editor.accept-revision（逐节点）   → 作者决定接受
Step 5 novelforge-v4.0.2.delivery.validate-delivery        → preflight（0 落盘；只统计 live issue）
Step 6 novelforge-v4.0.1.delivery.create-delivery-snapshot 或
       novelforge-v4.0.1.delivery.deliver-blueprint        → 建立交付
Step 7 novelforge-v4.0.1.delivery.inspect-delivery-manifest → 核对 revision / checksum
Step 8 novelforge-v4.0.1.delivery.download-delivery-artifact → 下载
Step 9 novelforge-v4.0.1.delivery.list-delivery-snapshots   → 记录交付凭据
```

## Expected result

一份 revision-pinned 交付物 + manifest（含 checksum），以及可回溯的快照列表。

## Verification

```text
· Step 5 preflight ok=true；不 ok 时先回到 Step 1–4
· 交付物非空且 checksum 与 manifest 一致
· Markdown / DOCX 内不含 internal 字段
· 交付前后 Blueprint revision 未被改动（delivery 只读）
```

V4.0.2 实测（PB-1 closure，默认/严格路径，无 explicit_revisions 绕过）：

```text
scene 植入占位缺陷 → accept → evaluate → preflight blocked
  codes = [DELIVERY_PLACEHOLDER_CONTENT, DELIVERY_Q9_BLOCKER, DELIVERY_QUALITY_FAILED]
  （证明真实 blocker 仍会拦截）
改回内容 → accept → evaluate（passed, issues=0）→ verify（resolved=2）
→ 默认 preflight ok=true、codes=[]
→ deliver（markdown / docx / nfpack）→ manifest 的 size / checksum 与下载内容一致
```

## Common failures

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `DELIVERY_VALIDATION_FAILED` | 未 accepted / 质量 blocker 仍在 | 回到 Step 1–4（不要放宽 policy） |
| 格式不可用 | 用了未注册格式 | 先读 `/studio/delivery/formats` |
| 只有部分节点被导出 | 其余未 accepted | 逐个 accept 或明确放宽（需作者决定） |

## Safety / invariants

```text
默认 accepted + quality pass；放宽必须显式且记录
delivery 不改真相、不调用模型
不在交付物里泄露 secret / 绝对路径
```

## Side effects

写交付快照 / manifest / artifact。

## Related skills

`create-new-story-blueprint`、`review-and-repair-blueprint`、
`novelforge-v4.0.2.delivery.validate-delivery`

## Source references

```text
skills/novelforge-v4.0.1/delivery/*（继承）+ skills/novelforge-v4.0.2/delivery/*
src/novelforge/delivery/**、src/novelforge/quality/store.py（live_issues）
tests/delivery/test_delivery_historical_quality.py
tests/browser_v4_studio_golden.cjs（真实下载 markdown / docx / nfpack）
docs/v4/V4_DELIVERY_CONTRACT.md §1、§6、§14
docs/v4/V4_0_2_STABILIZATION_REPORT.md
```
