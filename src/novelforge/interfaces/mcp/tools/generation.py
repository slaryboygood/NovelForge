"""Blueprint 生成工具（V4-08 §16）：MCP → application.services.blueprint → generation。"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from pydantic import Field

from ..contracts import ToolResult
from ..errors import MCPLLMUnavailable
from ..uri import node_uri
from . import MCPInput, build_tool

#: 生成任务 → tool 名（与 generation 的任务名一一对应）
GENERATION_TASKS: tuple[tuple[str, str, str], ...] = (
    ("generate_premise", "premise", "生成故事前提"),
    ("generate_theme", "theme", "生成主题"),
    ("generate_world", "world", "生成世界设定"),
    ("generate_character", "character", "生成人物"),
    ("generate_character_arc", "character_arc", "生成人物弧"),
    ("generate_story_arc", "story_arc", "生成故事主线结构"),
    ("generate_structural_unit", "structural_unit", "生成结构单元（幕 / 卷 / 篇章）"),
    ("generate_chapter_plan", "chapter", "生成章节卡"),
    ("generate_scene_plan", "scene", "生成场景卡"),
)


class GenerateInput(MCPInput):
    novel_id: str = Field(min_length=1, max_length=96)
    parent_id: str = Field(default="", max_length=64)
    node_id: str = Field(default="", max_length=64)
    expected_revision: int | None = Field(default=None, ge=1)
    sequence: int = Field(default=0, ge=0)
    idempotency_key: str = Field(default="", max_length=128)
    task_input: dict[str, Any] = Field(default_factory=dict)


def _generate(task: str) -> Callable[[Any, GenerateInput], ToolResult]:
    def impl(context: Any, payload: GenerateInput) -> ToolResult:
        if getattr(context, "blueprint", None) is None:
            raise MCPLLMUnavailable(
                "AI 生成不可用：MCP server 未配置 gateway（生成能力属于 Application 层）",
                details={"novel_id": payload.novel_id, "task": task})
        result = context.blueprint.generate_task(
            task, parent_id=payload.parent_id, node_id=payload.node_id,
            expected_revision=payload.expected_revision, sequence=payload.sequence,
            idempotency_key=payload.idempotency_key,
            task_input=dict(payload.task_input))
        node = dict(result.node or {})
        node_id = str(node.get("node_id") or "")
        return ToolResult(
            operation=task, novel_id=payload.novel_id, ok=bool(result.ok),
            revision=int(result.revision),
            result={"node": node, "contract": result.contract,
                    "model": result.model, "provider": result.provider,
                    "source_ids": list(result.source_ids),
                    "validation": dict(result.validation),
                    "node_status": node.get("status", ""),
                    "next": "review / accept 需要显式调用（不自动接受）"},
            usage=dict(result.usage or {}), warnings=tuple(result.warnings or ()),
            resources=(node_uri(payload.novel_id, node_id),) if node_id else (),
            summary=f"{task} → revision {result.revision}")
    return impl


def register(registry: Any) -> None:
    for name, task, description in GENERATION_TASKS:
        spec, handler = build_tool(
            name=name, description=f"{description}（proposal，不自动接受）",
            dto=GenerateInput,
            service="application.services.blueprint.generate_task",
            impl=_generate(task), expensive=True, idempotent=True,
            requires_revision=False, supports_dry_run=False,
            output_schema={"type": "object",
                           "properties": {"node": {"type": "object"},
                                          "revision": {"type": "integer"}}},
            possible_errors=("MCP_INVALID_ARGUMENT", "MCP_OWNERSHIP_MISMATCH",
                             "MCP_REVISION_CONFLICT", "MCP_LLM_UNAVAILABLE"))
        registry.register(spec, handler)


__all__ = ["GENERATION_TASKS", "GenerateInput", "register"]
