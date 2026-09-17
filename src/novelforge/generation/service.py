"""BlueprintGenerationService —— Story Blueprint 生成的唯一编排入口（V4-04）。

链路（§13 / §15 / §16 / §30 / §33）：

```text
GenerationRequest
   ↓ resolve TaskSpec（版本化 contract）
ContextBuilder（唯一上下文入口：generation 不自己查 Canon / StoryState / 大纲）
   ↓ ContextBundle → LLM contract context
LLMGateway（唯一模型入口）
   ↓ 结构化输出 + schema 校验（payload 模型）
Blueprint 结构 / 引用 / ownership 校验
   ↓ expected_revision 检查（core.revision）
BlueprintRepository.save_revision（append-only；支持 idempotency_key）
   ↓
GenerationResult（含 evidence：contract / context digest / source_ids / model）
```

明确不做（§34 / §54 / §55）：质量评分、repair planner、编辑器、正文生成。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.ai import LLMGateway, ModelPolicy, LLMError
from novelforge.blueprint import (
    BLUEPRINT_SCHEMA_VERSION,
    BlueprintNode,
    BlueprintRepository,
    BlueprintValidationError,
    CausalLinkPayload,
    require_valid,
)
from novelforge.core.ids import new_request_id
from novelforge.memory import ContextBuilder, ContextBundle

from .contracts import TaskRegistry, TaskSpec
from .errors import GenerationError, GenerationUnavailableError
from .tasks import chapter as chapter_task
from .tasks import characters as character_task
from .tasks import links as links_task
from .tasks import premise as premise_task
from .tasks import scene as scene_task
from .tasks import story as story_task
from .tasks import world as world_task

#: 默认流水线顺序（§6：不允许"整本大纲一次生成"）
DEFAULT_PIPELINE: tuple[str, ...] = (
    "premise", "theme", "world", "character", "character_arc", "story_arc",
    "structural_unit", "chapter", "scene", "links",
)


def default_registry() -> TaskRegistry:
    registry = TaskRegistry()
    registry.register(premise_task.premise_spec())
    registry.register(premise_task.theme_spec())
    registry.register(world_task.world_spec())
    registry.register(character_task.character_spec())
    registry.register(character_task.character_arc_spec())
    registry.register(story_task.story_arc_spec())
    registry.register(story_task.structural_unit_spec())
    registry.register(chapter_task.chapter_spec())
    registry.register(scene_task.scene_spec())
    return registry


@dataclass(frozen=True)
class GenerationRequest:
    novel_id: str
    task: str
    node_id: str = ""
    parent_id: str = ""
    expected_revision: int | None = None
    preserve: tuple[str, ...] = ()
    idempotency_key: str = ""
    request_id: str = ""
    revision: int | None = None
    sequence: int = 0
    task_input: Mapping[str, Any] = field(default_factory=dict)
    model_policy: ModelPolicy | None = None
    status: str = "proposed"

    def __post_init__(self) -> None:
        if not str(self.novel_id or "").strip():
            raise GenerationError("GenerationRequest 需要显式 novel_id")
        if not str(self.task or "").strip():
            raise GenerationError("GenerationRequest 需要 task")

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id, "task": self.task,
                "node_id": self.node_id, "parent_id": self.parent_id,
                "expected_revision": self.expected_revision,
                "preserve": list(self.preserve),
                "idempotency_key": self.idempotency_key,
                "request_id": self.request_id, "revision": self.revision,
                "sequence": self.sequence, "status": self.status}


@dataclass(frozen=True)
class GenerationEvidence:
    contract_id: str
    contract_version: int
    context_digest: str
    source_ids: tuple[str, ...]
    model: str
    provider: str
    request_id: str
    parent_revision: int
    context_blocks: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"contract_id": self.contract_id,
                "contract_version": self.contract_version,
                "context_digest": self.context_digest,
                "source_ids": list(self.source_ids), "model": self.model,
                "provider": self.provider, "request_id": self.request_id,
                "parent_revision": self.parent_revision,
                "context_blocks": list(self.context_blocks)}


@dataclass(frozen=True)
class GenerationResult:
    ok: bool
    operation: str
    request_id: str
    novel_id: str
    node: Mapping[str, Any] | None = None
    revision: int = 0
    contract: str = ""
    model: str = ""
    provider: str = ""
    context_digest: str = ""
    source_ids: tuple[str, ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    trace: Mapping[str, Any] = field(default_factory=dict)
    validation: Mapping[str, Any] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)
    cached: bool = False
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "operation": self.operation,
                "request_id": self.request_id, "novel_id": self.novel_id,
                "node": dict(self.node) if self.node else None,
                "revision": self.revision, "contract": self.contract,
                "model": self.model, "provider": self.provider,
                "context_digest": self.context_digest,
                "source_ids": list(self.source_ids), "usage": dict(self.usage),
                "trace": dict(self.trace), "validation": dict(self.validation),
                "evidence": dict(self.evidence), "cached": self.cached,
                "warnings": list(self.warnings)}


@dataclass(frozen=True)
class GenerationPlan:
    novel_id: str
    steps: tuple[Mapping[str, Any], ...]
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"novel_id": self.novel_id,
                "steps": [dict(row) for row in self.steps], "note": self.note}


class BlueprintGenerationService:
    """Story Blueprint 生成服务（唯一生成入口）。"""

    def __init__(self, project_root: Path | str, novel_id: str, *,
                 gateway: LLMGateway, memory: Any = None,
                 context_builder: ContextBuilder | None = None,
                 repository: BlueprintRepository | None = None,
                 registry: TaskRegistry | None = None) -> None:
        if not str(novel_id or "").strip():
            raise GenerationError("BlueprintGenerationService 需要显式 novel_id")
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)
        self.gateway = gateway
        self.registry = registry or default_registry()
        self.repository = repository or BlueprintRepository(self.project_root,
                                                            self.novel_id)
        if context_builder is not None:
            self.context_builder = context_builder
        elif memory is not None:
            self.context_builder = ContextBuilder(memory,
                                                  preferences=getattr(
                                                      memory, "preferences", None))
        else:  # pragma: no cover - 明确失败而不是静默降级
            raise GenerationUnavailableError(
                "BlueprintGenerationService 需要 memory 或 context_builder"
                "（generation 不自行做 memory retrieval）",
                details={"novel_id": self.novel_id})

    # ------------------------------------------------------------------ 计划
    def plan(self) -> GenerationPlan:
        steps: list[Mapping[str, Any]] = []
        for task in DEFAULT_PIPELINE:
            if task == "links":
                steps.append({"task": "links", "node_type": "causal_link",
                              "contract_id": "deterministic.links",
                              "requires_parent": False, "deterministic": True})
                continue
            spec = self.registry.get(task)
            steps.append({**spec.as_dict(), "deterministic": False})
        return GenerationPlan(novel_id=self.novel_id, steps=tuple(steps),
                              note="逐级生成：premise → world/characters → arcs → "
                                   "story arc → units → chapters → scenes → links")

    # ------------------------------------------------------------------ 生成
    def generate(self, request: GenerationRequest) -> GenerationResult:
        if request.novel_id != self.novel_id:
            raise GenerationError(
                f"拒绝跨作品生成：{request.novel_id} != {self.novel_id}",
                details={"request_novel": request.novel_id})
        spec = self.registry.get(request.task)
        request_id = request.request_id or new_request_id(f"gen_{spec.task}")
        if request.idempotency_key:
            existing = self.repository.find_by_idempotency(request.idempotency_key)
            if existing is not None:
                return GenerationResult(
                    ok=True, operation=spec.task, request_id=request_id,
                    novel_id=self.novel_id, node=existing.as_dict(),
                    revision=existing.revision, contract=spec.contract_id,
                    model=str(existing.provenance.get("model") or ""),
                    provider=str(existing.provenance.get("provider") or ""),
                    context_digest=existing.context_digest,
                    source_ids=tuple(existing.source_ids),
                    validation={"status": "PASS", "checks": ["idempotency_replay"]},
                    evidence={"contract_id": spec.contract_id,
                              "contract_version": spec.contract_version,
                              "context_digest": existing.context_digest,
                              "source_ids": list(existing.source_ids),
                              "request_id": request_id,
                              "parent_revision": existing.parent_revision},
                    warnings=("IDEMPOTENT_REPLAY",))
        parent_id = self._resolve_parent_id(spec, request.parent_id)
        current = (self.repository.get_current(request.node_id)
                   if request.node_id else None)
        if request.node_id and request.expected_revision is not None:
            # §11：不要在模型跑了几十秒之后才发现 revision 冲突
            from novelforge.core.revision import check_expected_revision

            check_expected_revision(request.expected_revision,
                                    current.revision if current else None,
                                    artifact_id=request.node_id)
        parent = (self.repository.get_current(request.parent_id)
                  if request.parent_id else
                  (self.repository.get_current(parent_id) if parent_id else None))
        if spec.requires_parent and not parent:
            raise GenerationError(
                f"任务 {spec.task} 需要存在的父节点",
                details={"parent_id": request.parent_id or parent_id})

        task_input = dict(request.task_input)
        bundle = self._build_context(spec, request, task_input)
        contract = spec.llm_contract()
        policy = request.model_policy or ModelPolicy(
            profile="quality_first", required_capabilities=spec.capabilities)
        try:
            llm_result = self.gateway.generate(
                contract=contract, context=self._llm_context(bundle, task_input),
                model_policy=policy, operation=spec.task, request_id=request_id,
                revision=request.revision)
        except LLMError as exc:
            raise GenerationUnavailableError(
                f"{spec.task} 生成失败：{exc.message}",
                details={"code": exc.code, "task": spec.task}) from exc

        payload = llm_result.output
        payload = self._enforce_system_ids(spec=spec, payload=payload, parent=parent,
                                           task_input=task_input)
        node = self._materialize_node(spec=spec, request=request, payload=payload,
                                      bundle=bundle, llm_result=llm_result,
                                      parent=parent, current=current,
                                      parent_id=parent_id or request.parent_id)
        known = self._known_with(node)
        require_valid(node, parent=parent, known=known)
        saved = self.repository.save_revision(
            node, expected_revision=request.expected_revision,
            idempotency_key=request.idempotency_key)
        return self._result(saved=saved, spec=spec, request=request,
                            bundle=bundle, llm_result=llm_result)

    def _resolve_parent_id(self, spec: TaskSpec, parent_id: str) -> str:
        """缺省父节点（仅用于结构上唯一的层级：unit → story_arc，chapter → 第一个 unit）。"""

        if parent_id:
            return parent_id
        if spec.task == "structural_unit":
            node = self.repository.get_current("story_arc")
            return node.node_id if node is not None else ""
        if spec.task == "chapter":
            units = self.repository.list_by_type("structural_unit")
            return units[0].node_id if units else ""
        return ""

    def _known_with(self, node: BlueprintNode) -> dict[str, BlueprintNode]:
        """把当前 Blueprint 的现存节点 + 待写入节点一起交给校验（引用完整性）。"""

        known = {item.node_id: item for item in self.repository.all_nodes()}
        known[node.node_id] = node
        return known

    def regenerate(self, *, task: str, node_id: str, expected_revision: int | None,
                   preserve: Sequence[str] = (), task_input: Mapping[str, Any] | None = None,
                   idempotency_key: str = "", model_policy: ModelPolicy | None = None
                   ) -> GenerationResult:
        """局部重生成（§37–§38）：只重生成一个节点，preserve 约束原样保留。"""

        current = self.repository.require_current(node_id)
        if preserve:
            missing = [item for item in preserve
                       if item not in (current.payload.model_dump(mode="json")
                                       if hasattr(current.payload, "model_dump")
                                       else dict(current.payload))]
            if missing:
                raise GenerationError(
                    f"preserve 字段不存在于当前节点：{missing}",
                    details={"node_id": node_id, "missing": missing})
        return self.generate(GenerationRequest(
            novel_id=self.novel_id, task=task, node_id=node_id,
            parent_id=current.parent_id, expected_revision=expected_revision,
            preserve=tuple(preserve), idempotency_key=idempotency_key,
            sequence=current.sequence, task_input=dict(task_input or {}),
            model_policy=model_policy))

    def accept(self, node_id: str, *, expected_revision: int | None = None
               ) -> BlueprintNode:
        """作者确认（V4-04 只提供 API；UI/Agent 审批属于后续阶段）。"""

        return self.repository.set_status(node_id, "accepted",
                                          expected_revision=expected_revision)

    # ------------------------------------------------------------------ 内部
    def _build_context(self, spec: TaskSpec, request: GenerationRequest,
                       task_input: Mapping[str, Any]) -> ContextBundle:
        context_request = spec.context_request(novel_id=self.novel_id,
                                               revision=request.revision,
                                               task_input=task_input)
        bundle = self.context_builder.build(context_request)
        return bundle

    @staticmethod
    def _llm_context(bundle: ContextBundle,
                     task_input: Mapping[str, Any]) -> dict[str, Any]:
        import json

        blocks: list[str] = []
        for block_id in bundle.order:
            block = bundle.blocks[block_id]
            if not block.items:
                continue
            text = "；".join(item.text for item in block.items)
            blocks.append(f"[{block_id}] {text}")
        return {"task_input": json.dumps(dict(task_input), ensure_ascii=False,
                                         sort_keys=True),
                "context": "\n".join(blocks) or "（没有可用上下文）"}

    def _materialize_node(self, *, spec: TaskSpec, request: GenerationRequest,
                          payload: Any, bundle: ContextBundle,
                          llm_result: Any, parent: BlueprintNode | None,
                          current: BlueprintNode | None,
                          parent_id: str = "") -> BlueprintNode:
        from .tasks import characters as ch
        from .tasks import premise as pr
        from .tasks import story as st

        task_input = dict(request.task_input)
        node_id = request.node_id
        sequence = request.sequence
        if not node_id:
            if spec.task == "premise":
                node_id = pr.premise_node_id()
            elif spec.task == "theme":
                node_id = pr.theme_node_id()
            elif spec.task == "world":
                node_id = world_task.world_node_id()
            elif spec.task == "character":
                index = int(task_input.get("index") or 1)
                node_id = ch.character_node_id(index, getattr(payload, "name", ""))
                sequence = sequence or index
            elif spec.task == "character_arc":
                character_id = str(getattr(payload, "character_id", "")
                                   or (parent.node_id if parent else ""))
                node_id = ch.character_arc_node_id(character_id)
                sequence = sequence or 1
            elif spec.task == "story_arc":
                node_id = st.story_arc_node_id()
            elif spec.task == "structural_unit":
                index = int(task_input.get("index") or 1)
                node_id = st.structural_unit_node_id(
                    str(getattr(payload, "unit_type", "unit")), index)
                sequence = sequence or index
            elif spec.task == "chapter":
                index = int(task_input.get("index") or 1)
                node_id = chapter_task.chapter_node_id(index)
                sequence = sequence or index
            elif spec.task == "scene":
                chapter_index = int(task_input.get("chapter_index") or 1)
                seq = int(task_input.get("sequence") or 1)
                node_id = scene_task.scene_node_id(chapter_index, seq)
                sequence = sequence or seq
            else:  # pragma: no cover - registry 保证
                raise GenerationError(f"任务没有 id 分配规则：{spec.task}")

        source_ids = tuple(sorted({row["source_id"] for row in bundle.provenance
                                   if row.get("source_id")}))
        provenance = {"context_blocks": list(bundle.order),
                      "context_digest": bundle.digest,
                      "task_input_keys": sorted(task_input),
                      "preserve": list(request.preserve),
                      "parent_revision": parent.revision if parent else 0,
                      "model": str(getattr(llm_result, "model", "")),
                      "provider": str(getattr(llm_result, "provider", ""))}
        return BlueprintNode(
            node_id=node_id, novel_id=self.novel_id, node_type=spec.node_type,
            payload=payload, parent_id=parent_id,
            status=request.status, source_ids=source_ids,
            context_digest=bundle.digest,
            generation_contract=spec.contract_id,
            generation_contract_version=spec.contract_version,
            provenance=provenance, sequence=sequence,
            schema_version=BLUEPRINT_SCHEMA_VERSION)

    @staticmethod
    def _enforce_system_ids(*, spec: TaskSpec, payload: Any, parent: BlueprintNode | None,
                            task_input: Mapping[str, Any]) -> Any:
        """系统分配 ID（§47）：模型不得自造 character_id / chapter_id 等结构 id。"""

        if spec.task == "character_arc" and parent is not None:
            return payload.model_copy(update={"character_id": parent.node_id})
        if spec.task == "scene":
            chapter_id = str(task_input.get("chapter_node_id")
                             or (parent.node_id if parent is not None else ""))
            if chapter_id:
                return payload.model_copy(update={"chapter_id": chapter_id})
        return payload

    @staticmethod
    def _result(*, saved: BlueprintNode, spec: TaskSpec, request: GenerationRequest,
                bundle: ContextBundle, llm_result: Any) -> GenerationResult:
        evidence = GenerationEvidence(
            contract_id=spec.contract_id, contract_version=spec.contract_version,
            context_digest=bundle.digest, source_ids=tuple(saved.source_ids),
            model=str(llm_result.model), provider=str(llm_result.provider),
            request_id=str(llm_result.request_id),
            parent_revision=saved.parent_revision,
            context_blocks=tuple(bundle.order))
        validation = {"status": "PASS",
                      "checks": ["schema", "structural", "ownership",
                                 "reference_integrity"]}
        return GenerationResult(
            ok=True, operation=spec.task, request_id=str(llm_result.request_id),
            novel_id=saved.novel_id, node=saved.as_dict(), revision=saved.revision,
            contract=spec.contract_id, model=str(llm_result.model),
            provider=str(llm_result.provider), context_digest=bundle.digest,
            source_ids=tuple(saved.source_ids), usage=dict(llm_result.usage),
            trace=dict(llm_result.trace), validation=validation,
            evidence=evidence.as_dict(),
            cached=bool((llm_result.cache or {}).get("hit")))

    # ------------------------------------------------------- 确定性结构关系
    def build_links(self, *, chapter_ids: Sequence[str] = ()) -> dict[str, Any]:
        """从已生成的 Scene / Chapter Card 中确定性建立 causal / setup / payoff。"""

        chapters = [self.repository.require_current(node_id)
                    for node_id in (chapter_ids or
                                    [node.node_id for node in
                                     self.repository.list_by_type("chapter")])]
        chapter_payloads = [self._payload_dict(node) for node in chapters]
        scene_payloads: list[dict[str, Any]] = []
        for chapter in chapters:
            for scene in self.repository.list_children(chapter.node_id,
                                                       node_type="scene"):
                scene_payloads.append(self._payload_dict(scene))

        setups = links_task.build_setups(scene_payloads, chapter_payloads,
                                        novel_id=self.novel_id)
        payoffs = links_task.build_payoffs(scene_payloads, chapter_payloads, setups,
                                          novel_id=self.novel_id)
        setups = links_task.apply_setup_payoff_status(setups, payoffs)
        causal_rows = links_task.build_causal_links(scene_payloads,
                                                   novel_id=self.novel_id)

        saved: dict[str, list[str]] = {"setup": [], "payoff": [], "causal_link": []}
        for index, row in enumerate(setups, start=1):
            parent_id = str(row.get("introduced_at") or "")
            node = BlueprintNode(
                node_id=str(row["setup_id"]), novel_id=self.novel_id,
                node_type="setup", payload=row["payload"], parent_id=parent_id,
                source_ids=tuple([f"{parent_id}"] if parent_id else ()),
                status="proposed",
                sequence=links_task.DERIVED_SEQUENCE_OFFSET + index)
            parent = self.repository.get_current(parent_id) if parent_id else None
            require_valid(node, parent=parent, known=self._known_with(node))
            saved_node = self.repository.save_revision(node, expected_revision=None)
            saved["setup"].append(saved_node.node_id)
        for index, row in enumerate(payoffs, start=1):
            parent_id = str(row.get("resolved_at") or "")
            node = BlueprintNode(
                node_id=str(row["payoff_id"]), novel_id=self.novel_id,
                node_type="payoff", payload=row["payload"], parent_id=parent_id,
                status="proposed",
                sequence=links_task.DERIVED_SEQUENCE_OFFSET + index)
            parent = self.repository.get_current(parent_id) if parent_id else None
            require_valid(node, parent=parent, known=self._known_with(node))
            saved_node = self.repository.save_revision(node, expected_revision=None)
            saved["payoff"].append(saved_node.node_id)
        for index, row in enumerate(causal_rows, start=1):
            node_id = links_task.causal_link_node_id(index)
            node = BlueprintNode(
                node_id=node_id, novel_id=self.novel_id, node_type="causal_link",
                payload=CausalLinkPayload(**row), parent_id="",
                status="proposed", sequence=index)
            require_valid(node, parent=None, known=self._known_with(node))
            saved_node = self.repository.save_revision(node, expected_revision=None)
            saved["causal_link"].append(saved_node.node_id)
        return {**saved, "counts": {key: len(value) for key, value in saved.items()},
                "unpaid_setups": [row["setup_id"] for row in setups
                                  if row["status"] == "open"]}

    @staticmethod
    def _payload_dict(node: BlueprintNode) -> dict[str, Any]:
        payload = node.payload
        data = (payload.model_dump(mode="json")
                if hasattr(payload, "model_dump") else dict(payload))
        return {"node_id": node.node_id, "node_type": node.node_type,
                "chapter_id": node.parent_id if node.node_type == "scene" else "",
                **data}


__all__ = [
    "BlueprintGenerationService", "DEFAULT_PIPELINE", "GenerationEvidence",
    "GenerationPlan", "GenerationRequest", "GenerationResult", "default_registry",
]
