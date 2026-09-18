"""JourneyService —— 唯一 JourneyProjection 入口（ADR-004）。

为什么存在：V3 里同一本书的「阶段 / 进度 / 下一步」有两个计算入口
（`story_builder/v3_projection._journey_projection()` 与 `story_builder/ui_flow.py` 自己的
stage/next-step），这与 NF-005 的修复目标冲突。V4-01 把**入口**收敛到服务层；
post-release cleanup 之后，**实现**也收敛到 current 产品层：

```text
UI（Story Studio Overview）
REST（/api/story-builder/studio/overview）
MCP（novelforge://novel/<id> 摘要里的 journey 段）
        ↓
JourneyService → JourneyProjection（唯一公式）
```

真相来源**只有 current 产品层**（不再 import 任何 V2/V3 Story Builder 后端）：

```text
Project / novel context   NovelProfileRepository（title / genre / content pack）
Blueprint                 BlueprintRepository（节点类型 · 状态 · revision）
Quality                   QualityStore（报告结论 + open blocker）
Delivery readiness        DeliveryStore（已生成的交付快照）
```

硬边界：

```text
· 只读：不写 profile / Blueprint / Quality / Delivery，也不创建目录
· 不伪造：每个 objective 都带 evidence（真实计数 / 真实结论），没有数据就报未开始
· 确定性：全部是纯规则函数（无随机、无 LLM）
· 不新增事实层：不建 Journey 数据库 / 状态机 / 并行 story truth
```
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from novelforge.blueprint import BlueprintRepository
from novelforge.delivery import DeliveryStore
from novelforge.quality.store import QualityStore
from novelforge.story_engine.profile import NovelProfile, NovelProfileRepository

#: V4 阶段词表（唯一一套）：id / 展示名 / 图标 / 该阶段真正要达成的事
V4_STAGES: tuple[dict[str, str], ...] = (
    {"stage_id": "premise", "label": "创意", "icon": "creation",
     "goal": "把想法定成一句话能说清的前提"},
    {"stage_id": "structure", "label": "结构", "icon": "story",
     "goal": "世界 / 人物 / 故事弧成形"},
    {"stage_id": "scenes", "label": "场景", "icon": "simulation",
     "goal": "每场戏都能说清「为什么存在」"},
    {"stage_id": "review", "label": "检查", "icon": "review",
     "goal": "质量门都有结论、阻塞项清零"},
    {"stage_id": "delivery", "label": "交付", "icon": "export",
     "goal": "产出可交付的版本"},
)

STAGE_INDEX: dict[str, int] = {row["stage_id"]: index
                               for index, row in enumerate(V4_STAGES)}

#: V4 阶段 → Story Studio 一级工作区（**纯展示映射**，不参与任何进度计算）
STAGE_TO_DISPLAY_GROUP: dict[str, str] = {
    "premise": "creation",
    "structure": "story",
    "scenes": "scenes",
    "review": "quality",
    "delivery": "delivery",
}

#: objective_id → 作者点得动的下一步（target_view 必须是 Story Studio 一级工作区）
_OBJECTIVE_ACTIONS: dict[str, dict[str, str]] = {
    "premise": {"action_id": "define_premise", "title": "写下这本书的前提",
                "action_label": "生成前提", "target_view": "creation",
                "impact": "没有前提，后面的世界 / 人物 / 章节都无处附着"},
    "world": {"action_id": "shape_world", "title": "把世界规则写清楚",
              "action_label": "生成世界", "target_view": "world",
              "impact": "世界规则决定哪些情节真的可能发生"},
    "characters": {"action_id": "cast_characters", "title": "确定主要人物",
                   "action_label": "生成人物", "target_view": "characters",
                   "impact": "人物欲望与错误信念决定冲突走向"},
    "arc": {"action_id": "sketch_arc", "title": "搭出故事弧",
            "action_label": "生成故事弧", "target_view": "story",
            "impact": "没有弧线，章节只是离散片段"},
    "units": {"action_id": "define_units", "title": "划分结构单元 / 章节",
              "action_label": "生成结构单元", "target_view": "story",
              "impact": "结构单元是场景的挂载点"},
    "scenes": {"action_id": "write_scenes", "title": "写关键场景卡",
               "action_label": "生成场景", "target_view": "scenes",
               "impact": "场景卡说明每场戏为什么必须存在"},
    "quality_report": {"action_id": "evaluate_quality", "title": "跑一次质量检查",
                       "action_label": "去检查", "target_view": "quality",
                       "impact": "没有检查结论，交付就是盲发"},
    "no_open_blocker": {"action_id": "repair_blockers", "title": "修复阻塞项",
                        "action_label": "修复阻塞项", "target_view": "quality",
                        "impact": "阻塞项会让交付门直接失败"},
    "delivery_snapshot": {"action_id": "deliver_snapshot", "title": "交付一个版本",
                          "action_label": "去交付", "target_view": "delivery",
                          "impact": "只有落盘的快照才是可交付成果"},
}

ALL_COMPLETE_ACTION: dict[str, str] = {
    "action_id": "extend_story",
    "title": "五个阶段都已完成：可以继续打磨或交付新版本",
    "action_label": "继续打磨", "target_view": "story",
    "impact": "当前没有未完成的阶段，继续加深比重复检查更有价值",
}


def _objective(objective_id: str, stage_id: str, label: str, detail: str,
               done: int, total: int, evidence: Mapping[str, Any], *,
               optional: bool = False) -> dict[str, Any]:
    """构造一个带 evidence 的 objective（done/total 只能来自真实读取结果）。"""

    done = max(0, min(int(done), int(total)))
    if optional:
        status = "optional"
    elif total > 0 and done >= total:
        status = "complete"
    elif done > 0:
        status = "active"
    else:
        status = "available"
    return {"objective_id": objective_id, "stage_id": stage_id, "label": label,
            "detail": detail, "optional": bool(optional), "status": status,
            "progress": {"done": done, "total": int(total),
                         "label": f"{done}/{int(total)}"},
            "evidence": dict(evidence)}


class JourneyService:
    """按 (project_root, novel_id) 计算只读 JourneyProjection（不写任何文件）。"""

    def __init__(self, project_root: Path | str, novel_id: str) -> None:
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id or "").strip()
        if not self.novel_id:
            raise ValueError("JourneyService 需要显式 novel_id（不允许隐式当前作品）")

    # ------------------------------------------------------------------ 投影
    def projection(self) -> dict[str, Any]:
        """唯一进度投影：阶段 / 目标 / 进度 / 下一步（只读，全部来自 current truth）。"""

        profile: NovelProfile = NovelProfileRepository(self.project_root).load(
            self.novel_id)
        nodes = BlueprintRepository(self.project_root, self.novel_id).all_nodes()
        quality = QualityStore(self.project_root, self.novel_id)
        report = quality.latest_report()
        issues = quality.list_issues()
        snapshots = DeliveryStore(self.project_root, self.novel_id).list_snapshots()
        return self._assemble(profile, nodes, report, issues, snapshots)

    def display_group(self, projection: Mapping[str, Any] | None = None) -> str:
        """当前阶段对应的一级工作区（Studio 侧栏），调用方可复用已算好的投影。"""

        data = projection if projection is not None else self.projection()
        stage = str((data.get("journey") or {}).get("current_stage") or "")
        return STAGE_TO_DISPLAY_GROUP.get(stage, "creation")

    def next_action(self) -> Mapping[str, Any]:
        """当前推荐下一步（来自同一投影，不允许调用方自行推导）。"""

        return self.projection().get("next_action") or {}

    # ------------------------------------------------------------------ 组装
    def _assemble(self, profile: NovelProfile, nodes: list[Any],
                  report: Mapping[str, Any], issues: list[dict[str, Any]],
                  snapshots: list[dict[str, Any]]) -> dict[str, Any]:
        by_type: Counter[str] = Counter(str(node.node_type) for node in nodes)
        accepted = sum(1 for node in nodes if str(node.status) == "accepted")
        blocked_open = [row for row in issues
                        if str(row.get("severity")) == "blocker"
                        and str(row.get("status")) == "open"]

        objectives = [
            _objective("premise", "premise", "定下前提",
                       "一句话说清主角想要什么、什么挡着他",
                       1 if by_type["premise"] else 0, 1,
                       {"node_type": "premise", "count": by_type["premise"]}),
            _objective("world", "structure", "世界规则",
                       "规则 / 地点 / 势力至少有一个真实节点",
                       1 if by_type["world"] else 0, 1,
                       {"node_type": "world", "count": by_type["world"]}),
            _objective("characters", "structure", "主要人物",
                       "至少一张人物卡",
                       1 if by_type["character"] else 0, 1,
                       {"node_type": "character", "count": by_type["character"]}),
            _objective("arc", "structure", "故事弧",
                       "主线至少一条故事弧",
                       1 if by_type["story_arc"] else 0, 1,
                       {"node_type": "story_arc", "count": by_type["story_arc"]}),
            _objective("units", "structure", "结构单元 / 章节",
                       "结构单元（或章节）是场景的挂载点",
                       min(1, by_type["structural_unit"] + by_type["chapter"]), 1,
                       {"structural_units": by_type["structural_unit"],
                        "chapters": by_type["chapter"]}),
            _objective("scenes", "scenes", "场景卡",
                       "每场戏都要说清「为什么存在」",
                       min(1, by_type["scene"]), 1,
                       {"node_type": "scene", "count": by_type["scene"]}),
            _objective("quality_report", "review", "一次质量检查",
                       "至少有一份质量报告（passed / failed / blocked 都算有结论）",
                       1 if report else 0, 1,
                       {"report_id": str(report.get("report_id") or ""),
                        "status": str(report.get("status") or "unevaluated"),
                        "gates": len(report.get("gates") or [])}),
            _objective("no_open_blocker", "review", "阻塞项清零",
                       "open 状态的 blocker 必须为 0",
                       1 if not blocked_open else 0, 1,
                       {"open_blockers": len(blocked_open),
                        "issue_ids": [str(row.get("issue_id") or "")
                                      for row in blocked_open][:5]}),
            _objective("delivery_snapshot", "delivery", "交付快照",
                       "至少有一个已生成的交付快照",
                       1 if snapshots else 0, 1,
                       {"snapshots": len(snapshots),
                        "latest": str((snapshots[-1] if snapshots else {}).get(
                            "snapshot_id") or "")}),
        ]

        stages: list[dict[str, Any]] = []
        current_stage = ""
        for stage in V4_STAGES:
            rows = [row for row in objectives if row["stage_id"] == stage["stage_id"]]
            counted = [row for row in rows if not row["optional"]]
            done = sum(row["progress"]["done"] for row in counted)
            total = sum(row["progress"]["total"] for row in counted)
            progress = {"done": done, "total": total,
                        "percent": round(100 * done / total) if total else 0}
            if not current_stage and done < total:
                current_stage = stage["stage_id"]
            stages.append({**stage, "progress": progress,
                           "objective_ids": [row["objective_id"] for row in rows]})
        if not current_stage:
            current_stage = V4_STAGES[-1]["stage_id"]
        current_index = STAGE_INDEX[current_stage]
        for index, stage in enumerate(stages):
            if index < current_index:
                status = "COMPLETE"
            elif index == current_index:
                status = ("IN_PROGRESS" if stage["progress"]["done"]
                          < stage["progress"]["total"] else "CURRENT")
            elif index == current_index + 1:
                status = "AVAILABLE"
            else:
                status = "LOCKED"
            stage["status"] = status
            stage["current"] = index == current_index
            stage["reachable"] = status in ("COMPLETE", "CURRENT", "IN_PROGRESS",
                                            "AVAILABLE")

        counted_objectives = [row for row in objectives if not row["optional"]]
        total_done = sum(row["progress"]["done"] for row in counted_objectives)
        total_items = sum(row["progress"]["total"] for row in counted_objectives)
        percent = round(100 * total_done / total_items) if total_items else 0

        current_objective = next(
            (row for row in objectives
             if row["stage_id"] == current_stage
             and row["status"] not in ("complete", "optional")), None)
        if current_objective is None:
            current_objective = next((row for row in objectives
                                      if row["status"] not in ("complete",
                                                               "optional")), None)
        next_action = self._next_action(current_objective, current_stage)

        return {
            "novel_id": self.novel_id,
            "profile": profile,
            "objectives": objectives,
            "stages": stages,
            "current_stage": current_stage,
            "current_objective": current_objective,
            "progress": {"percent": percent, "label": "总体进度",
                         "done": total_done, "total": total_items},
            "journey": {
                "stages": stages,
                "current_stage": current_stage,
                "current_stage_label": next((row["label"] for row in stages
                                             if row["stage_id"] == current_stage), ""),
                "current_stage_goal": next((row["goal"] for row in stages
                                            if row["stage_id"] == current_stage), ""),
                "recommended_next_stage": (
                    stages[current_index + 1]["stage_id"]
                    if current_index + 1 < len(stages) else ""),
                "completed_stages": sum(1 for row in stages
                                        if row["status"] == "COMPLETE"),
                "stage_count": len(stages),
            },
            "facts": {
                "blueprint_nodes": len(nodes),
                "blueprint_accepted": accepted,
                "blueprint_by_type": dict(sorted(by_type.items())),
                "quality_status": str(report.get("status") or "unevaluated"),
                "quality_reports": 1 if report else 0,
                "open_blockers": len(blocked_open),
                "delivery_snapshots": len(snapshots),
            },
            "next_action": next_action,
            "read_only": True,
        }

    @staticmethod
    def _next_action(current_objective: Mapping[str, Any] | None,
                     current_stage: str) -> dict[str, Any]:
        if current_objective is None:
            return {"stage_id": current_stage, "objective_id": "",
                    "reason": ALL_COMPLETE_ACTION["title"],
                    "deep_link": {"view": ALL_COMPLETE_ACTION["target_view"],
                                  "step": "", "group": ""},
                    **ALL_COMPLETE_ACTION}
        objective_id = str(current_objective.get("objective_id") or "")
        spec = _OBJECTIVE_ACTIONS.get(objective_id) or ALL_COMPLETE_ACTION
        return {"stage_id": current_stage, "objective_id": objective_id,
                "reason": str(current_objective.get("detail") or ""),
                "deep_link": {"view": spec["target_view"], "step": objective_id,
                              "group": current_stage},
                **spec}


def journey_service(project_root: Path | str, novel_id: str) -> JourneyService:
    """工厂函数：`journey_service(root, novel_id).projection()`。"""

    return JourneyService(project_root, novel_id)


__all__ = ["ALL_COMPLETE_ACTION", "JourneyService", "STAGE_INDEX",
           "STAGE_TO_DISPLAY_GROUP", "V4_STAGES", "journey_service"]
