"""Generation 契约与任务注册表（V4-04 §7、§12、§43–§45）。

每个生成任务对应**版本化 LLM Contract**（`blueprint.<task>.v1`），
并声明：输入要求 / 输出 schema / context policy / model capability /
generation mode / timeout / retry / structured output policy。

禁止用 `generic_story_generator` 处理所有任务。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from pydantic import BaseModel

from novelforge.ai import LLMContract, PromptSpec, ValidationPolicy
from novelforge.blueprint import PAYLOAD_MODELS
from novelforge.memory import ContextRequest

from .errors import GenerationError

#: 任务 → (LLM contract id, 版本)
CONTRACT_VERSION = 1


@dataclass(frozen=True)
class TaskSpec:
    """一个 Blueprint 生成任务的完整声明。"""

    task: str
    node_type: str
    output_model: type[BaseModel]
    system_prompt: str
    requires_parent: bool = False
    parent_types: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ("creative", "structured_output")
    token_budget: int = 900
    max_output_tokens: int = 2000
    timeout_s: float = 90.0
    max_attempts: int = 2
    context_types: tuple[str, ...] = ()
    include_preferences: bool = True
    top_k: int = 6
    cacheable: bool = False
    temperature_policy: str = "creative"
    description: str = ""
    extra_context_keys: tuple[str, ...] = ()

    @property
    def contract_id(self) -> str:
        return f"blueprint.{self.task}.v{CONTRACT_VERSION}"

    @property
    def contract_version(self) -> int:
        return CONTRACT_VERSION

    def llm_contract(self) -> LLMContract:
        return LLMContract(
            contract_id=self.contract_id, version=self.contract_version,
            prompt=PromptSpec(
                system=self.system_prompt,
                user_template="任务输入：\n{task_input}\n\n---\n可用上下文：\n{context}\n"),
            output_model=self.output_model, generation_mode="structured_json",
            temperature_policy=self.temperature_policy,  # type: ignore[arg-type]
            max_output_tokens=self.max_output_tokens, timeout_s=self.timeout_s,
            max_attempts=self.max_attempts, cacheable=self.cacheable,
            validation=ValidationPolicy(require_json=True,
                                        retry_on_structured_output=True,
                                        strict=False),
            required_capabilities=self.capabilities)

    def context_request(self, *, novel_id: str, revision: int | None,
                        task_input: Mapping[str, Any]) -> ContextRequest:
        """把任务声明翻译成 ContextRequest（generation 不自己拼上下文，§15）。"""

        characters = tuple(str(value) for value in (task_input.get("characters") or ())
                           if str(value))
        locations = tuple(str(value) for value in (task_input.get("locations") or ())
                          if str(value))
        return ContextRequest(
            novel_id=novel_id, revision=revision, operation=self.task,
            target_kind=self.node_type,
            target_id=str(task_input.get("parent_id") or ""),
            task=str(task_input.get("task") or self.description or self.task),
            characters=characters, locations=locations,
            memory_types=self.context_types, token_budget=self.token_budget,
            required_source_ids=tuple(str(value) for value in
                                      (task_input.get("required_source_ids") or ())),
            include_preferences=self.include_preferences, top_k=self.top_k)

    def as_dict(self) -> dict[str, Any]:
        return {"task": self.task, "node_type": self.node_type,
                "contract_id": self.contract_id,
                "contract_version": self.contract_version,
                "requires_parent": self.requires_parent,
                "parent_types": list(self.parent_types),
                "capabilities": list(self.capabilities),
                "token_budget": self.token_budget,
                "max_output_tokens": self.max_output_tokens,
                "timeout_s": self.timeout_s, "max_attempts": self.max_attempts,
                "context_types": list(self.context_types),
                "cacheable": self.cacheable,
                "output_schema": getattr(self.output_model, "__name__", "")}


class TaskRegistry:
    """任务注册表（确定性顺序；每个任务一个 contract）。"""

    def __init__(self, specs: Mapping[str, TaskSpec] | None = None) -> None:
        self._specs: dict[str, TaskSpec] = dict(specs or {})

    def register(self, spec: TaskSpec) -> TaskSpec:
        if spec.node_type not in PAYLOAD_MODELS:
            raise GenerationError(f"未注册的蓝图层节点类型：{spec.node_type}")
        if spec.output_model is not PAYLOAD_MODELS[spec.node_type]:
            raise GenerationError(
                f"任务 {spec.task} 的 output_model 必须复用 blueprint payload 模型")
        self._specs[spec.task] = spec
        return spec

    def get(self, task: str) -> TaskSpec:
        spec = self._specs.get(task)
        if spec is None:
            raise GenerationError(
                f"未知生成任务：{task}", details={"known": sorted(self._specs)})
        return spec

    def tasks(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    def all(self) -> tuple[TaskSpec, ...]:
        return tuple(self._specs[task] for task in self.tasks())

    def __len__(self) -> int:
        return len(self._specs)


__all__ = ["CONTRACT_VERSION", "TaskRegistry", "TaskSpec"]

