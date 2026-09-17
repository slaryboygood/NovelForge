"""M6：PlotNode synthesis —— 压力 → PlotNode Candidate → 校验 → promote。

硬边界：

- LLM / 规则只产出 `PlotNodeCandidate`（proposal DTO），**不能直接写 repository**；
- 只有 `approved=True` 且没有 blocking finding 的 candidate 才能经 `promote_candidate`
  成为新的 Planning revision（旧 revision 保持 immutable）；
- 不生成 StorySpine（那是 StorySpineBuilder 的职责），不分章、不做 Route Lab。
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable, Protocol

from pydantic import ValidationError

from .findings import AnalysisReport, PlanningFinding, add_finding
from .models import PlotNodeCandidate, PlotProposal, StoryPlanningIR
from .plot_pressure import PlotPressureInventory, build_plot_pressure_inventory
from .repository import PlanningRepository, PlanningRevisionRecord
from .schemas import validate_planning_ir
from .spine_analysis import analyze_story_spine

BACKOFF = (2.0, 5.0, 10.0)
SYSTEM_PROMPT = (
    "你是长篇小说剧情节点提案助手，只提出结构化 PlotNode 候选，不写正文、不改 Planning。"
    "输入是当前 Planning revision 的切片与压力清单；每个候选必须引用真实存在的稳定 ID，"
    "并给出简短设计理由摘要（不是推理过程）。"
    "输出严格 JSON：{\"candidates\":[{\"candidate_id\":\"CAND_...\",\"pressure_refs\":[...],"
    "\"proposed_node\":{...},\"proposed_edges\":[...],\"reasoning_summary\":\"...\"}]}。"
    "只输出 JSON。")


class PlotProposalError(RuntimeError):
    def __init__(self, code: str, message: str, *, raw: str = "") -> None:
        self.code = code
        self.message = message
        self.raw = raw
        super().__init__(f"{code}: {message}")


class PlotCandidateProvider(Protocol):
    def propose(self, payload: dict[str, Any], *,
                source_revision: str) -> list[PlotNodeCandidate]: ...


class StaticPlotCandidateProvider:
    """测试 / fixture 用：直接给出候选 JSON（仍走 strict schema）。"""

    def __init__(self, candidates: list[dict[str, Any]], *, provider: str = "static",
                 model: str = "static") -> None:
        self.candidates = candidates
        self.provider = provider
        self.model = model

    def propose(self, payload: dict[str, Any], *,
                source_revision: str) -> list[PlotNodeCandidate]:
        rows = []
        for item in self.candidates:
            document = dict(item)
            document.setdefault("provider", self.provider)
            document.setdefault("model", self.model)
            document.setdefault("source_revision", source_revision)
            document.setdefault("provenance", "generated")
            try:
                rows.append(PlotNodeCandidate.model_validate(document, strict=True))
            except ValidationError as exc:
                raise PlotProposalError("PLOT_CANDIDATE_SCHEMA_INVALID",
                                        str(exc)[:300]) from exc
        return rows


class LLMPlotCandidateProvider:
    """可选 LLM provider（compatibility adapter over `novelforge.ai`）。

    `chat` 可注入（测试不需要网络）；未注入时经 `ai.chat_completion_via_gateway`
    调用模型 —— 本模块不再自带 HTTP 客户端，也没有写死的厂商端点 / 模型。
    """

    MODEL_ENV = "NOVELFORGE_PLOT_MODEL"
    BASE_URL_ENV = "NOVELFORGE_PLOT_BASE_URL"

    def __init__(self, *, api_key: str = "", model: str = "",
                 base_url: str = "",
                 timeout: float = 150.0, max_attempts: int = 3,
                 chat: Callable[[list[dict[str, str]]], str] | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_attempts = max_attempts
        self._injected = chat is not None
        self._chat = chat or self._gateway_chat

    def propose(self, payload: dict[str, Any], *,
                source_revision: str) -> list[PlotNodeCandidate]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
        last_error: PlotProposalError | None = None
        for attempt in range(1, self.max_attempts + 1):
            raw = self._chat(messages)
            try:
                return parse_candidates(raw, source_revision=source_revision,
                                        provider="llm", model=self.model)
            except PlotProposalError as error:
                last_error = error
                if attempt < self.max_attempts:
                    time.sleep(BACKOFF[min(attempt - 1, len(BACKOFF) - 1)])
        assert last_error is not None
        raise last_error

    def _gateway_chat(self, messages: list[dict[str, str]]) -> str:
        """经 `novelforge.ai` 调用（V4-02：legacy 调用不再自己发 HTTP）。"""

        from novelforge.ai import LLMError, chat_completion_via_gateway
        from novelforge.ai.legacy_support import map_legacy_error_code

        try:
            text = chat_completion_via_gateway(
                messages, model=self.model, base_url=self.base_url,
                api_key=self.api_key, timeout_s=self.timeout,
                max_output_tokens=4000, operation="plot_candidates",
                provider_id="plot_candidates", model_env=self.MODEL_ENV,
                base_url_env=self.BASE_URL_ENV, system_prompt=SYSTEM_PROMPT)
        except LLMError as exc:
            raise PlotProposalError(
                map_legacy_error_code(exc, http_code="PLOT_PROPOSAL_HTTP_FAILURE",
                                      network_code="PLOT_PROPOSAL_NETWORK_FAILURE"),
                exc.message[:200]) from exc
        if not str(text or "").strip():
            raise PlotProposalError("PLOT_PROPOSAL_EMPTY_RESPONSE", "模型返回空内容")
        return str(text)


def parse_candidates(raw: str, *, source_revision: str, provider: str,
                     model: str) -> list[PlotNodeCandidate]:
    """strict schema：非法 JSON / 形状错误 / 字段类型错误分别拒绝。"""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PlotProposalError("PLOT_PROPOSAL_JSON_INVALID", str(exc)[:200], raw=raw) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise PlotProposalError("PLOT_PROPOSAL_SHAPE_INVALID",
                                "响应必须是 {\"candidates\": [...]}", raw=raw)
    rows: list[PlotNodeCandidate] = []
    for item in payload["candidates"]:
        if not isinstance(item, dict):
            raise PlotProposalError("PLOT_PROPOSAL_SHAPE_INVALID", "candidate 必须是对象")
        document = dict(item)
        document.setdefault("source_revision", source_revision)
        document.setdefault("provider", provider)
        document.setdefault("model", model)
        try:
            rows.append(PlotNodeCandidate.model_validate(document, strict=True))
        except ValidationError as exc:
            raise PlotProposalError("PLOT_CANDIDATE_SCHEMA_INVALID",
                                    str(exc)[:300], raw=raw) from exc
    return rows


def build_synthesis_payload(plan: StoryPlanningIR, *, revision_id: str = "",
                            inventory: PlotPressureInventory | None = None,
                            max_pressures: int = 20) -> dict[str, Any]:
    """给 provider 的最小上下文：revision + 目标压力 + 相关切片（不塞整本 JSON）。"""

    inventory = inventory or build_plot_pressure_inventory(plan, revision_id=revision_id)
    pressures = [item for item in inventory.pressures
                 if item.state in ("open", "blocked")][:max_pressures]
    focus_ids: set[str] = set()
    for pressure in pressures:
        focus_ids.add(pressure.source_ref)
        focus_ids.update(pressure.affected_refs)
    from .context import StoryPlanningContextBuilder

    builder = StoryPlanningContextBuilder(plan, revision_id=revision_id)
    slices = {}
    for purpose in ("character", "relationship", "faction", "location", "information",
                    "progression", "resource", "equipment", "base", "map",
                    "autonomous_action", "reward", "plot"):
        context = builder.build(purpose, ids=focus_ids)
        slices[purpose] = {"included_ids": context.included_ids,
                           "boundary": context.boundary,
                           "payload": context.payload}
    return {"planning_revision": revision_id or "working",
            "planning_id": plan.planning_id,
            "novel_id": plan.novel_id,
            "pressures": [item.model_dump(mode="json") for item in pressures],
            "slices": slices,
            "story_spine": {"nodes": list(plan.spine.nodes) if plan.spine else [],
                            "edges": [edge.model_dump(mode="json")
                                      for edge in (plan.spine.edges if plan.spine else [])]}}


def propose_candidates(plan: StoryPlanningIR, provider: PlotCandidateProvider, *,
                       revision_id: str = "", inventory: PlotPressureInventory | None = None
                       ) -> PlotProposal:
    payload = build_synthesis_payload(plan, revision_id=revision_id, inventory=inventory)
    candidates = provider.propose(payload, source_revision=revision_id)
    digest = hashlib.sha1(f"{plan.planning_id}:{revision_id}".encode("utf-8")).hexdigest()[:10]
    proposal = PlotProposal(proposal_id=f"PPROP_{digest.upper()}",
                            novel_id=plan.novel_id, source_revision=revision_id,
                            provider=getattr(provider, "provider", "static"),
                            model=getattr(provider, "model", ""), candidates=candidates)
    for candidate in proposal.candidates:
        candidate.validation_findings = [
            item.model_dump(mode="json")
            for item in validate_candidate(plan, candidate, inventory=inventory).findings]
    return proposal


def validate_candidate(plan: StoryPlanningIR, candidate: PlotNodeCandidate, *,
                       inventory: PlotPressureInventory | None = None,
                       available_requirements: tuple[str, ...] = ()) -> AnalysisReport:
    """在候选被合入后的**副本**上跑 M6 校验；不修改原 plan。"""

    from .spine_builder import StorySpineBuilder

    builder = StorySpineBuilder(novel_id=plan.novel_id)
    merged = builder.build_plan(plan, nodes=[candidate.proposed_node],
                               edges=candidate.proposed_edges)
    report = analyze_story_spine(merged, inventory=inventory,
                                 available_requirements=available_requirements)
    known = {item.node_id for item in merged.plot_nodes}
    findings = [item for item in report.findings
                if item.source_id == candidate.proposed_node.node_id
                or candidate.proposed_node.node_id in item.related_ids
                or item.severity == "ERROR"]
    extra: list[PlanningFinding] = []
    for pressure_id in candidate.pressure_refs:
        if inventory is not None and inventory.by_id(pressure_id) is None:
            add_finding(extra, "CANDIDATE_PRESSURE_REF_UNKNOWN", "WARNING", "plot",
                        candidate.candidate_id, "候选引用的压力不在导入清单里",
                        related=(pressure_id,))
    if candidate.proposed_node.node_id not in known:
        add_finding(extra, "CANDIDATE_NODE_MISSING", "ERROR", "plot",
                    candidate.candidate_id, "候选没有提供有效 proposed_node")
    return AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                          findings=findings + extra)


def promote_candidate(repository: PlanningRepository, base_revision_id: str,
                      candidate: PlotNodeCandidate, *, note: str = "",
                      revision_id: str = "", require_approved: bool = True
                      ) -> PlanningRevisionRecord:
    """把候选合入新的 Planning revision；旧 revision 不变（immutable）。"""

    if require_approved and not candidate.approved:
        raise PlotProposalError("CANDIDATE_NOT_APPROVED",
                                "candidate 必须先被显式 approve 才能 promote")
    if candidate.blocking():
        raise PlotProposalError("CANDIDATE_HAS_BLOCKING_FINDINGS",
                                "candidate 存在 blocking ERROR，不能 promote")
    base = repository.load(base_revision_id)
    from .spine_builder import StorySpineBuilder

    builder = StorySpineBuilder(novel_id=base.novel_id)
    plan = builder.build_plan(base.plan, nodes=[candidate.proposed_node],
                              edges=candidate.proposed_edges)
    return repository.create(plan, branch_id=base.branch_id, status="proposed",
                             note=note or f"promote {candidate.candidate_id}",
                             parent_revision_id=base.revision_id,
                             source_revision=base.revision_id, revision_id=revision_id)


__all__ = [
    "LLMPlotCandidateProvider",
    "PlotCandidateProvider",
    "PlotProposalError",
    "StaticPlotCandidateProvider",
    "build_synthesis_payload",
    "parse_candidates",
    "promote_candidate",
    "propose_candidates",
    "validate_candidate",
]
