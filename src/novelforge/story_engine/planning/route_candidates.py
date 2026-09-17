"""M7：Planning Route Lab V2 —— RouteCandidate（patch 形式的未来方案）。

与旧 runtime Route Lab v1 的边界：v1 操作 StoryState 分支（fork / replay / merge happened
effects），M7 只操作 **Planning revision 的 patch**，候选是 immutable / disposable /
non_authoritative 的提案；只有作者显式 promote 才会产生新的 Planning revision。
"""

from __future__ import annotations

import json
from typing import Any, Callable, Literal

from pydantic import Field, ValidationError

from novelforge.models import StrictModel

from .findings import AnalysisReport, PlanningFinding, add_finding
from .models import PlotNode, SpineEdge, StoryPlanningIR, new_planning_id
from .schemas import validate_planning_ir
from .versioning import planning_digest

ROUTE_CANDIDATE_SCHEMA = 1
RouteScope = Literal["macro", "volume_window", "spine_segment", "around_node",
                     "pressure_cluster", "ending_direction", "custom"]
RouteCandidateStatus = Literal["draft", "validated", "blocked", "ready", "rejected",
                               "promoted", "superseded"]
FORBIDDEN_PATCH_PREFIXES: tuple[str, ...] = ("ENTITY_", "FACT_", "EVENT_", "KNW_", "REL_",
                                             "FS_", "CON_", "uuid_")
FORBIDDEN_PATCH_KEYS: tuple[str, ...] = ("canon", "story_state", "happened", "occurred",
                                         "storystate")


class RouteCandidatePatch(StrictModel):
    """对 source revision 的结构化 patch（不是整本 Planning 副本）。"""

    add_nodes: list[PlotNode] = Field(default_factory=list)
    modify_nodes: list[PlotNode] = Field(default_factory=list)
    remove_node_ids: list[str] = Field(default_factory=list)
    add_edges: list[SpineEdge] = Field(default_factory=list)
    remove_edges: list[SpineEdge] = Field(default_factory=list)
    requirement_bindings: dict[str, list[str]] = Field(default_factory=dict)
    pressure_states: dict[str, str] = Field(default_factory=dict)
    conflict_chain_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def touched_node_ids(self) -> set[str]:
        rows = {item.node_id for item in self.add_nodes}
        rows |= {item.node_id for item in self.modify_nodes}
        rows |= set(self.remove_node_ids)
        return rows


class RouteCandidate(StrictModel):
    """候选路线：proposal artifact，`non_authoritative=True`，不写 Planning / Canon / StoryState。"""

    schema_version: int = ROUTE_CANDIDATE_SCHEMA
    candidate_id: str = Field(min_length=6, max_length=64)
    source_planning_revision_id: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    title: str = Field(default="", max_length=120)
    summary: str = Field(default="", max_length=400)
    scope: RouteScope = "spine_segment"
    target_node_ids: list[str] = Field(default_factory=list)
    patch: RouteCandidatePatch = Field(default_factory=RouteCandidatePatch)
    pressure_resolution_plan: dict[str, str] = Field(default_factory=dict)
    expected_impacts: dict[str, list[str]] = Field(default_factory=dict)
    reasoning_summary: str = Field(default="", max_length=400)
    provider: str = Field(default="manual", max_length=64)
    model: str = Field(default="", max_length=64)
    status: RouteCandidateStatus = "draft"
    approved: bool = False
    validation_findings: list[PlanningFinding] = Field(default_factory=list)
    non_authoritative: Literal[True] = True

    def blocking(self) -> bool:
        return any(item.severity == "ERROR" for item in self.validation_findings)

    def is_stale(self, plan: StoryPlanningIR, *, current_revision_id: str = "") -> bool:
        if self.source_digest and self.source_digest != planning_digest(plan):
            return True
        return bool(current_revision_id and self.source_planning_revision_id
                    and current_revision_id != self.source_planning_revision_id)


class RouteCandidateConflict(StrictModel):
    """rebase / compose 的冲突（作者手工处理，不自动 merge）。"""

    code: str = Field(default="ROUTE_CANDIDATE_CONFLICT", max_length=64)
    node_id: str = Field(default="", max_length=64)
    message: str = Field(default="", max_length=300)
    details: dict[str, Any] = Field(default_factory=dict)


class RouteProposalError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def new_candidate_id(key: str = "") -> str:
    return new_planning_id("candidate", key or "ROUTE")


def check_patch_scope(patch: RouteCandidatePatch, plan: StoryPlanningIR) -> list[PlanningFinding]:
    """patch 只能改未来 Planning；触碰 Canon / StoryState / 已排期事实一律 ERROR。"""

    findings: list[PlanningFinding] = []
    payload = patch.model_dump(mode="json")
    for key in _walk_keys(payload):
        if key.lower() in FORBIDDEN_PATCH_KEYS:
            add_finding(findings, "ROUTE_CANDIDATE_TOUCHES_HAPPENED_TRUTH", "ERROR", "route",
                        "patch", "patch 试图携带 Canon / StoryState 字段", related=(key,))
    nodes_by_id = {node.node_id: node for node in plan.plot_nodes}
    for node_id in patch.touched_node_ids():
        if any(node_id.startswith(prefix) for prefix in FORBIDDEN_PATCH_PREFIXES):
            add_finding(findings, "ROUTE_CANDIDATE_TOUCHES_HAPPENED_TRUTH", "ERROR", "route",
                        node_id, "patch 试图修改 Canon / StoryState 命名空间的对象")
        node = nodes_by_id.get(node_id)
        if node is not None and node.scheduled_volume_id and node.must_happen \
                and node_id in patch.remove_node_ids:
            # 已确认排期的 must_happen 仍是 future Planning anchor，不是 happened truth：
            # 这里用独立的 Planning conflict 表达，避免与 Canon / StoryState 混淆。
            add_finding(findings, "ROUTE_REMOVES_CONFIRMED_PLANNING_ANCHOR", "ERROR", "route",
                        node_id, "patch 试图删除已排期的 must_happen planning anchor",
                        related=(node.scheduled_volume_id,))
    return findings


def materialize_candidate(plan: StoryPlanningIR, candidate: RouteCandidate,
                          *, require_ready: bool = False) -> StoryPlanningIR:
    """source revision + patch → 临时 Planning 副本（用于 validation / compare）。"""

    if require_ready and candidate.status not in ("ready", "promoted", "validated"):
        raise RouteProposalError("ROUTE_CANDIDATE_NOT_READY",
                                 f"candidate status={candidate.status}")
    findings = check_patch_scope(candidate.patch, plan)
    if findings:
        raise RouteProposalError(findings[0].code, findings[0].message)
    payload = plan.model_dump(mode="json")
    nodes = {item.node_id: item for item in plan.plot_nodes}
    for node in candidate.patch.modify_nodes:
        if node.node_id not in nodes:
            raise RouteProposalError("ROUTE_PATCH_MODIFY_UNKNOWN_NODE", node.node_id)
        nodes[node.node_id] = node
    for node in candidate.patch.add_nodes:
        nodes[node.node_id] = node
    for node_id in candidate.patch.remove_node_ids:
        nodes.pop(node_id, None)
    payload["plot_nodes"] = [item.model_dump(mode="json") for item in nodes.values()]
    # requirement bindings → satisfied_by（只改 Planning 语义）
    for node in payload["plot_nodes"]:
        group = node.get("requirements")
        if not group:
            continue
        for ref in group.get("requirements", []):
            binding = candidate.patch.requirement_bindings.get(ref.get("requirement_id", ""))
            if binding:
                ref["satisfied_by"] = list(binding)
    spine = plan.spine
    if spine is not None:
        edges = {(edge.from_node_id, edge.to_node_id, edge.relation)
                 for edge in spine.edges}
        for edge in candidate.patch.remove_edges:
            edges.discard((edge.from_node_id, edge.to_node_id, edge.relation))
        for edge in candidate.patch.add_edges:
            if edge.from_node_id not in nodes or edge.to_node_id not in nodes:
                raise RouteProposalError("ROUTE_PATCH_EDGE_UNKNOWN_NODE",
                                         f"{edge.from_node_id}->{edge.to_node_id}")
            edges.add((edge.from_node_id, edge.to_node_id, edge.relation))
        known = set(nodes)
        spine_payload = spine.model_dump(mode="json")
        spine_payload["nodes"] = sorted(known)
        spine_payload["edges"] = [{"from_node_id": source, "to_node_id": target,
                                   "relation": relation}
                                  for source, target, relation in sorted(edges)
                                  if source in known and target in known]
        spine_payload["entry_node_ids"] = [item for item in spine_payload["entry_node_ids"]
                                           if item in known]
        spine_payload["terminal_node_ids"] = [item for item in spine_payload["terminal_node_ids"]
                                              if item in known]
        payload["spine"] = spine_payload
    return validate_planning_ir(payload)


class StaticRouteCandidateProvider:
    """测试 / 手工用：直接给出候选（仍走 strict schema）。"""

    def __init__(self, candidates: list[dict[str, Any]], *, provider: str = "static",
                 model: str = "static") -> None:
        self.candidates = candidates
        self.provider = provider
        self.model = model

    def propose(self, payload: dict[str, Any], *,
                source_revision: str, source_digest: str) -> list[RouteCandidate]:
        rows: list[RouteCandidate] = []
        for item in self.candidates:
            document = dict(item)
            document.setdefault("source_planning_revision_id", source_revision)
            document.setdefault("source_digest", source_digest)
            document.setdefault("provider", self.provider)
            document.setdefault("model", self.model)
            try:
                rows.append(RouteCandidate.model_validate(document, strict=True))
            except ValidationError as exc:
                raise RouteProposalError("ROUTE_CANDIDATE_SCHEMA_INVALID",
                                         str(exc)[:300]) from exc
        return rows


class LLMRouteCandidateProvider:
    """可选 LLM provider（compatibility adapter over `novelforge.ai`）。

    只产出 proposal，`chat` 可注入（CI 不需要网络）；未注入时经
    `ai.chat_completion_via_gateway` 调用，本模块不再自带 HTTP 客户端。
    """

    MODEL_ENV = "NOVELFORGE_ROUTE_MODEL"
    BASE_URL_ENV = "NOVELFORGE_ROUTE_BASE_URL"

    def __init__(self, *, api_key: str = "", model: str = "",
                 base_url: str = "",
                 timeout: float = 150.0,
                 chat: Callable[[list[dict[str, str]]], str] | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self._injected = chat is not None
        self._chat = chat or self._gateway_chat

    def propose(self, payload: dict[str, Any], *, source_revision: str,
                source_digest: str) -> list[RouteCandidate]:
        messages = [{"role": "system", "content": ROUTE_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
        raw = self._chat(messages)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RouteProposalError("ROUTE_PROPOSAL_JSON_INVALID", str(exc)[:200]) from exc
        rows = body.get("candidates") if isinstance(body, dict) else None
        if not isinstance(rows, list):
            raise RouteProposalError("ROUTE_PROPOSAL_SHAPE_INVALID",
                                     "响应必须是 {\"candidates\": [...]}")
        provider = StaticRouteCandidateProvider(rows, provider="llm", model=self.model)
        return provider.propose(payload, source_revision=source_revision,
                                source_digest=source_digest)

    def _gateway_chat(self, messages: list[dict[str, str]]) -> str:  # pragma: no cover
        """经 `novelforge.ai` 调用（V4-02：legacy 调用不再自己发 HTTP）。"""

        from novelforge.ai import LLMError, chat_completion_via_gateway
        from novelforge.ai.legacy_support import map_legacy_error_code

        try:
            return chat_completion_via_gateway(
                messages, model=self.model, base_url=self.base_url,
                api_key=self.api_key, timeout_s=self.timeout,
                max_output_tokens=4000, operation="route_candidates",
                provider_id="route_candidates", model_env=self.MODEL_ENV,
                base_url_env=self.BASE_URL_ENV, system_prompt=ROUTE_SYSTEM_PROMPT)
        except LLMError as exc:
            raise RouteProposalError(
                map_legacy_error_code(exc, http_code="ROUTE_PROPOSAL_HTTP_FAILURE",
                                      network_code="ROUTE_PROPOSAL_NETWORK_FAILURE"),
                exc.message[:200]) from exc


ROUTE_SYSTEM_PROMPT = (
    "你是长篇小说路线方案助手，只提出结构化路线候选（对某个 Planning revision 的 patch），"
    "不写正文、不做评分真值、不自动采用。输出严格 JSON：{\"candidates\":[{\"candidate_id\":"
    "\"CAND_...\",\"title\":\"...\",\"summary\":\"...\",\"scope\":\"spine_segment\","
    "\"patch\":{\"add_nodes\":[],\"modify_nodes\":[],\"remove_node_ids\":[],"
    "\"add_edges\":[],\"remove_edges\":[],\"requirement_bindings\":{},\"pressure_states\":{}},"
    "\"reasoning_summary\":\"...\"}]}。只输出 JSON。")


def _walk_keys(payload: Any):
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield str(key)
            yield from _walk_keys(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_keys(item)


def candidate_summary(candidate: RouteCandidate) -> dict[str, Any]:
    """只读摘要（UI / compare 用，不参与 truth）。"""

    return {"candidate_id": candidate.candidate_id, "title": candidate.title,
            "status": candidate.status, "scope": candidate.scope,
            "source_revision": candidate.source_planning_revision_id,
            "add_nodes": [item.node_id for item in candidate.patch.add_nodes],
            "remove_nodes": list(candidate.patch.remove_node_ids),
            "modify_nodes": [item.node_id for item in candidate.patch.modify_nodes],
            "add_edges": [(item.from_node_id, item.to_node_id, item.relation)
                          for item in candidate.patch.add_edges],
            "remove_edges": [(item.from_node_id, item.to_node_id, item.relation)
                             for item in candidate.patch.remove_edges],
            "non_authoritative": True}


__all__ = [
    "FORBIDDEN_PATCH_KEYS",
    "FORBIDDEN_PATCH_PREFIXES",
    "LLMRouteCandidateProvider",
    "ROUTE_CANDIDATE_SCHEMA",
    "ROUTE_SYSTEM_PROMPT",
    "RouteCandidate",
    "RouteCandidateConflict",
    "RouteCandidatePatch",
    "RouteCandidateStatus",
    "RouteProposalError",
    "RouteScope",
    "StaticRouteCandidateProvider",
    "candidate_summary",
    "check_patch_scope",
    "materialize_candidate",
    "new_candidate_id",
]
