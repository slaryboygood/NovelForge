"""字段级 AI Rewrite 契约（V4-06 §17–§20、§58）。

与 `regenerate` 的区别（§18）：

```text
regenerate  重新生成整个节点（整段 payload）
rewrite     只改 target_fields，其余字段必须保持与当前 revision 一致
```

因此 rewrite 的 contract 是**版本化**的（`blueprint.<task>.rewrite.v1`），并且：

```text
1. 模型输出仍按 payload 模型做 schema 校验（复用同一个 output_model）
2. 除 target_fields 外任何字段发生变化 → RewriteViolationError（不落盘）
3. 合并时只取 target_fields（其余一律沿用当前 revision）→ 结构性不可能被改写
```
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from novelforge.ai import LLMContract, PromptSpec, ValidationPolicy

from .contracts import TaskSpec
from .errors import RewriteViolationError

REWRITE_CONTRACT_VERSION = 1


def rewrite_contract_id(task: str) -> str:
    return f"blueprint.{task}.rewrite.v{REWRITE_CONTRACT_VERSION}"


def rewrite_system_prompt(*, task: str, target_fields: Sequence[str],
                          preserve_fields: Sequence[str]) -> str:
    targets = "、".join(str(field) for field in target_fields)
    preserve = "、".join(str(field) for field in preserve_fields) or "（无额外声明）"
    return (
        f"你是故事蓝图编辑器。只允许改写这些字段：{targets}。"
        f"其它所有字段必须与给定当前值完全一致（尤其是：{preserve}）。"
        "不得发明既定事实、不得改变人物身份、不得改变结构关系（父节点 / 章节归属 / 人物 id）。"
        "输出必须是完整 JSON 对象（包含所有字段，未授权字段照抄当前值）。只输出 JSON。")


def build_rewrite_contract(spec: TaskSpec, *, target_fields: Sequence[str],
                           preserve_fields: Sequence[str] = (),
                           instruction: str = "") -> LLMContract:
    """构造 rewrite 的 LLM contract（用户模板与生成共用 task_input/context 两个键）。"""

    system = rewrite_system_prompt(task=spec.task, target_fields=target_fields,
                                   preserve_fields=preserve_fields)
    user_template = (
        "改写指令：\n{instruction}\n\n"
        "---- 当前 revision 内容 ----\n{current}\n\n"
        "---- 可用上下文 ----\n{context}\n")
    return LLMContract(
        contract_id=rewrite_contract_id(spec.task), version=REWRITE_CONTRACT_VERSION,
        prompt=PromptSpec(system=system, user_template=user_template),
        output_model=spec.output_model, generation_mode="structured_json",
        temperature_policy=spec.temperature_policy,  # type: ignore[arg-type]
        max_output_tokens=spec.max_output_tokens, timeout_s=spec.timeout_s,
        max_attempts=spec.max_attempts, cacheable=False,
        validation=ValidationPolicy(require_json=True,
                                    retry_on_structured_output=True, strict=False),
        required_capabilities=spec.capabilities)


def fields_of(payload_model: Any) -> tuple[str, ...]:
    fields = getattr(payload_model, "model_fields", None)
    if isinstance(fields, Mapping):
        return tuple(sorted(str(name) for name in fields))
    return ()


def changed_outside_target(current: Mapping[str, Any], proposed: Mapping[str, Any],
                           target_fields: Sequence[str]) -> tuple[str, ...]:
    """模型输出里除 target_fields 之外被改动的字段（§20、§58）。"""

    targets = {str(field) for field in target_fields}
    names = set(current) | set(proposed)
    return tuple(sorted(str(name) for name in names
                        if name not in targets
                        and current.get(name) != proposed.get(name)))


def merge_target_fields(current: Mapping[str, Any], proposed: Mapping[str, Any],
                        target_fields: Sequence[str]) -> dict[str, Any]:
    """只把 target_fields 从模型输出合并进当前 payload（其余字段绝不改动）。"""

    merged = dict(current)
    for field in target_fields:
        key = str(field)
        if key in proposed:
            merged[key] = proposed[key]
    return merged


def assert_rewrite_allowed(*, payload_fields: Sequence[str],
                           target_fields: Sequence[str],
                           preserve_fields: Sequence[str]) -> tuple[tuple[str, ...],
                                                                  tuple[str, ...]]:
    """校验 target / preserve 合法（返回规范化后的两个 tuple）。"""

    known = {str(field) for field in payload_fields}
    targets = tuple(dict.fromkeys(str(field) for field in target_fields if str(field)))
    preserve = tuple(dict.fromkeys(str(field) for field in preserve_fields if str(field)))
    if not targets:
        raise RewriteViolationError("rewrite 必须显式声明 target_fields")
    unknown = sorted(set(targets) - known)
    if unknown:
        raise RewriteViolationError(f"这些字段不属于该节点：{unknown}",
                                    fields=unknown, details={"known_fields": sorted(known)})
    overlap = sorted(set(targets) & set(preserve))
    if overlap:
        raise RewriteViolationError(f"target_fields 与 preserve_fields 冲突：{overlap}",
                                    fields=overlap)
    return targets, preserve


__all__ = [
    "REWRITE_CONTRACT_VERSION", "assert_rewrite_allowed", "build_rewrite_contract",
    "changed_outside_target", "fields_of", "merge_target_fields",
    "rewrite_contract_id", "rewrite_system_prompt",
]
