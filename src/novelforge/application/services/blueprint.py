"""BlueprintService —— 业务层使用 Story Blueprint 的统一入口（V4-04 §52）。

为将来的 REST / MCP / Agent / UI 提供同一个入口：

```text
generate(request)     逐级生成一个节点
regenerate(...)       局部重生成（只改一个节点）
accept(node_id)       作者确认
plan()                生成计划
read(node_id) / tree()  只读查询
build_links(...)      确定性建立 causal / setup / payoff
validate()            结构 / 引用 / ownership 校验
```

本模块只做编排与只读查询；生成逻辑在 `novelforge.generation`，
存储与校验在 `novelforge.blueprint`。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.blueprint import BlueprintRepository, validate_graph
from novelforge.generation import (
    BlueprintGenerationService,
    GenerationRequest,
    GenerationResult,
)


class BlueprintService:
    """Blueprint 生成与读取的业务入口（依赖注入 generation / repository）。"""

    def __init__(self, project_root: Path | str, novel_id: str, *,
                 generation: BlueprintGenerationService,
                 repository: BlueprintRepository | None = None) -> None:
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)
        self.generation = generation
        self.repository = repository or generation.repository

    # ------------------------------------------------------------------ 生成
    def generate(self, request: GenerationRequest) -> GenerationResult:
        return self.generation.generate(request)

    def generate_task(self, task: str, **kwargs: Any) -> GenerationResult:
        return self.generation.generate(GenerationRequest(
            novel_id=self.novel_id, task=task, **kwargs))

    def regenerate(self, *, task: str, node_id: str,
                   expected_revision: int | None, **kwargs: Any) -> GenerationResult:
        return self.generation.regenerate(task=task, node_id=node_id,
                                          expected_revision=expected_revision,
                                          **kwargs)

    def accept(self, node_id: str, *, expected_revision: int | None = None):
        return self.generation.accept(node_id, expected_revision=expected_revision)

    def plan(self):
        return self.generation.plan()

    def build_links(self, *, chapter_ids: Sequence[str] = ()) -> dict[str, Any]:
        return self.generation.build_links(chapter_ids=chapter_ids)

    # ------------------------------------------------------------------ 读取
    def read(self, node_id: str) -> dict[str, Any] | None:
        node = self.repository.get_current(node_id)
        return node.as_dict() if node is not None else None

    def revisions(self, node_id: str) -> list[int]:
        return self.repository.list_revisions(node_id)

    def children(self, parent_id: str, *, node_type: str = "") -> list[dict[str, Any]]:
        return [node.as_dict()
                for node in self.repository.list_children(parent_id,
                                                          node_type=node_type)]

    def tree(self) -> dict[str, Any]:
        nodes = self.repository.all_nodes()
        by_type: dict[str, int] = {}
        for node in nodes:
            by_type[node.node_type] = by_type.get(node.node_type, 0) + 1
        return {"novel_id": self.novel_id, "node_count": len(nodes),
                "by_type": dict(sorted(by_type.items())),
                "nodes": [node.as_dict() for node in nodes]}

    def validate(self) -> dict[str, Any]:
        return validate_graph(self.repository.all_nodes(), novel_id=self.novel_id)

    def stats(self) -> Mapping[str, Any]:
        nodes = self.repository.all_nodes()
        by_status: dict[str, int] = {}
        for node in nodes:
            by_status[node.status] = by_status.get(node.status, 0) + 1
        return {"novel_id": self.novel_id, "nodes": len(nodes),
                "by_status": dict(sorted(by_status.items())),
                "schema_version": self.repository.index_snapshot().get("schema_version")}


def blueprint_service(project_root: Path | str, novel_id: str, *,
                      generation: BlueprintGenerationService,
                      repository: BlueprintRepository | None = None) -> BlueprintService:
    return BlueprintService(project_root, novel_id, generation=generation,
                            repository=repository)


__all__ = ["BlueprintService", "blueprint_service"]

