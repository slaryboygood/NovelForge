"""Q3 Continuity（V4-05 §15）：结构化的时间 / 地点 / 信息 / 关系连续性检查。"""

from __future__ import annotations

import re
from typing import Any, Sequence

from ..contracts import QualityEvidence, QualityIssue, make_issue
from ..registry import EvaluatorRegistry, EvaluatorSpec
from .base import EvaluationContext, stable_scope, text_of

EVALUATOR_ID = "quality.continuity.v1"

DAY_PATTERN = re.compile(r"第\s*(\d+)\s*[天日]")
TRANSITION_MARKERS = ("前往", "移动到", "返回", "抵达", "离开", "转移", "穿过")


def _scenes(context: EvaluationContext) -> list[Any]:
    scenes = context.nodes_of_type("scene")
    if context.scope.node_ids:
        allowed = set(context.scope.node_ids)
        scoped = [node for node in scenes if node.node_id in allowed]
        if scoped:
            return scoped
    return scenes


def _day_of(payload: dict[str, Any]) -> int | None:
    match = DAY_PATTERN.search(str(payload.get("time") or ""))
    return int(match.group(1)) if match else None


def evaluate(context: EvaluationContext) -> Sequence[QualityIssue]:
    issues: list[QualityIssue] = []
    scenes = _scenes(context)
    if len(scenes) < 2:
        return issues

    payloads = [context.payload(node) for node in scenes]

    # 1. 时间：显式「第 N 天」必须单调不退
    days = [(_day_of(payload), node) for payload, node in zip(payloads, scenes)]
    known = [(day, node) for day, node in days if day is not None]
    for (prev_day, prev_node), (day, node) in zip(known, known[1:]):
        if day < prev_day:
            scope = stable_scope(node)
            evidence = QualityEvidence(
                evidence_id=f"{node.node_id}:time",
                kind="comparison",
                explanation=f"{prev_node.node_id} 在第 {prev_day} 天，"
                            f"{node.node_id} 却在第 {day} 天（时间倒退）",
                node_ids=(prev_node.node_id, node.node_id), revision=node.revision,
                comparison={"prev": payloads[scenes.index(prev_node)].get("time"),
                            "current": payloads[scenes.index(node)].get("time")})
            issues.append(make_issue(
                code="CONTINUITY_TIME_CONFLICT", novel_id=context.novel_id,
                scope=scope, reason="场景时间顺序倒退", evidence=[evidence],
                evaluator_id=EVALUATOR_ID,
                provenance={"prev_node": prev_node.node_id}))

    # 2. 地点：相邻场景切换地点但没有过渡标记
    for prev, current in zip(scenes, scenes[1:]):
        prev_payload, current_payload = context.payload(prev), context.payload(current)
        if not prev_payload.get("location") or not current_payload.get("location"):
            continue
        if prev_payload["location"] == current_payload["location"]:
            continue
        combined = text_of(current_payload, "scene_purpose", "escalation", "turn",
                           "outcome", "character_goals")
        if any(marker in combined for marker in TRANSITION_MARKERS):
            continue
        scope = stable_scope(current)
        evidence = QualityEvidence(
            evidence_id=f"{current.node_id}:location",
            kind="comparison",
            explanation=f"从 {prev_payload['location']} 到 {current_payload['location']}，"
                        f"但本场没有描述移动/过渡",
            node_ids=(prev.node_id, current.node_id), revision=current.revision,
            comparison={"from": prev_payload["location"],
                        "to": current_payload["location"]})
        issues.append(make_issue(
            code="CONTINUITY_LOCATION_CONFLICT", novel_id=context.novel_id,
            scope=scope, reason="地点跳转缺少过渡", evidence=[evidence],
            evaluator_id=EVALUATOR_ID))

    # 3. 信息知晓：后续场景使用的信息必须在此前揭示过
    revealed: list[str] = []
    for node, payload in zip(scenes, payloads):
        uses: list[str] = []
        for row in payload.get("state_transition_intent") or []:
            if isinstance(row, dict) and row.get("kind") == "knowledge":
                target = str(row.get("target") or "").strip()
                if target:
                    uses.append(target)
        for item in uses:
            if item in revealed:
                continue
            repeated = any(item in str(previous.get("information_reveal") or [])
                           + str(previous.get("outcome") or "")
                           for previous in payloads[:payloads.index(payload)])
            if repeated:
                continue
            scope = stable_scope(node)
            evidence = QualityEvidence(
                evidence_id=f"{node.node_id}:knowledge:{item}",
                kind="graph",
                explanation=f"{node.node_id} 计划让角色使用「{item}」，"
                            f"但此前没有任何场景揭示它",
                node_ids=(node.node_id,), revision=node.revision,
                comparison={"knowledge": item,
                            "revealed_so_far": sorted(set(revealed))})
            issues.append(make_issue(
                code="CONTINUITY_KNOWLEDGE_LEAK", novel_id=context.novel_id,
                scope=scope, reason=f"信息在揭示前被使用：{item}",
                evidence=[evidence], evaluator_id=EVALUATOR_ID, suffix=item))
        revealed.extend(str(value) for value in (payload.get("information_reveal") or []))

    # 4. 关系变化：声明了变化但本场没有对应功能
    for node, payload in zip(scenes, payloads):
        change = str(payload.get("relationship_change") or "").strip()
        if not change:
            continue
        functions = set(payload.get("story_function") or [])
        if "relationship_change" in functions:
            continue
        scope = stable_scope(node)
        evidence = QualityEvidence(
            evidence_id=f"{node.node_id}:relationship",
            kind="node_field",
            explanation=f"声明了关系变化「{change[:80]}」，但 story_function 未包含 "
                        f"relationship_change",
            node_ids=(node.node_id,), revision=node.revision,
            comparison={"story_function": sorted(functions)})
        issues.append(make_issue(
            code="CONTINUITY_RELATIONSHIP_CONFLICT", novel_id=context.novel_id,
            scope=scope, reason="关系变化缺少结构支撑", evidence=[evidence],
            evaluator_id=EVALUATOR_ID))
    return issues


def register(registry: EvaluatorRegistry) -> None:
    registry.register(EvaluatorSpec(
        evaluator_id=EVALUATOR_ID, version=1, gate="Q3", kind="deterministic",
        supported_node_types=("scene",),
        required_context=("blueprint_nodes",),
        description="时间 / 地点 / 信息 / 关系的结构化连续性"),
        evaluate)


__all__ = ["EVALUATOR_ID", "evaluate", "register"]

