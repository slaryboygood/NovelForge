"""M16B Writer Integration：分层 writer context + draft + Draft Fact Sync。

repo 定义（V2 里程碑，见 docs/CHANGELOG.md）：M16B = 「Writer Integration +
Draft Fact Sync（事实校验 → 产品入口与回写通道）」。

结构：

```text
Frozen Truth / Planning / Chapter IR
        ↓
WriterContextBuilder（分层：canon / occurred / historical_repair / planned / guidance）
        ↓
WriterPackage（复用 story_engine.writer.build_writer_package）
        ↓
Writer（复用 writer.render_scene / fallback_text + 外部 writer 的 claims）
        ↓
validate_writer_output（既有校验）+ Draft Fact Sync（只产生 proposal，不写事实）
```

边界：writer 不自行解析 Canon / 不判断 occurred vs planned；写作输出与事实提议全部
保存在 `preview` 层，**不写 StoryState / Canon**。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.story_engine.creator import DEFAULT_BRANCH, resolve_creator_context
from novelforge.story_engine.historical_ir import HISTORY_DIR, HistoricalIRStore
from novelforge.story_engine.memory_view import memory_snapshot
from novelforge.story_engine.outline_forge import load_forge_chain
from novelforge.story_engine.settings_gen import load_pack_draft, saved_pack_id
from novelforge.story_engine.storage import StoryStateRepository
from novelforge.story_engine.writer import (
    WriterClaim,
    WriterOutput,
    build_writer_package,
    fallback_text,
    render_scene,
    validate_writer_output,
)
from novelforge.story_engine.world_view import world_snapshot

# ---------------------------------------------------------------- writer store
# 写作草稿的 canonical 存储（唯一 SSOT）：
#
#   novel/authoring/story_engine/writer/<novel_id>/index.json   ← 草稿索引
#   novel/authoring/story_engine/writer/<novel_id>/drafts/*.json
#
# 这里同时被「写入（WriterDraftService）」与「读取（v3_projection 投影 /
# export）」使用，因此产品的 create / read / update / projection / progress /
# export 只有一个来源。历史路径只读兼容（见 LEGACY_WRITER_STORE_DIR）。
WRITER_STORE_DIR = "novel/authoring/story_engine/writer"
# V2 M16B 早期把草稿写在 workspace 下（gitignored，可能已有作者数据）：
# 保留只读回退，不再写入，避免同一语义对象出现两个写入源。
LEGACY_WRITER_STORE_DIR = "workspace/wasteland_001_exports/writer_v1"
# 兼容旧常量名（旧调用点 / 旧测试）：值就是 canonical 路径。
WRITER_DIR = WRITER_STORE_DIR
CONTEXT_FORMAT_VERSION = "m16-writer-context-1"
BLOCK_BUDGET = 40

CANON_DB = "novel/authoring/story_engine/canon/wasteland_001.sqlite"

TRUTH_BLOCKS: tuple[tuple[str, str, int], ...] = (
    ("canon_truth", "occurred", 0),
    ("story_state", "occurred", 1),
    ("historical_repair", "historical_repair", 2),
    ("planning", "planned", 3),
    ("chapter_plan", "planned", 4),
    ("writer_guidance", "ui_derived", 5),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")


def _digest(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _history_dir(project_root: Path | str) -> Path:
    local = Path(project_root) / HISTORY_DIR
    if (local / "index.json").is_file():
        return local
    return Path(__file__).resolve().parents[3] / HISTORY_DIR


# ------------------------------------------------------- writer store（SSOT）
def writer_store_path(project_root: Path | str, novel_id: str, *,
                      writer_dir: str = WRITER_DIR) -> Path:
    """canonical writer draft 目录（写入口与读入口共用这一个函数）。"""

    return Path(project_root).resolve() / writer_dir / novel_id


def writer_index_path(project_root: Path | str, novel_id: str, *,
                      writer_dir: str = WRITER_DIR) -> Path:
    return writer_store_path(project_root, novel_id, writer_dir=writer_dir) / "index.json"


def draft_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """草稿索引里的一行（只含列表页需要的信息，不含草稿正文）。"""

    validation = payload.get("validation") or {}
    fact_sync = payload.get("fact_sync") or {}
    return {
        "draft_id": str(payload.get("draft_id") or ""),
        "chapter_id": str(payload.get("chapter_id") or ""),
        "event_id": str(payload.get("event_id") or ""),
        "accepted": bool(validation.get("accepted")) if isinstance(
            validation, Mapping) else False,
        "synced": bool(fact_sync.get("synced")) if isinstance(fact_sync, Mapping) else False,
        "generated_at": str(payload.get("generated_at") or ""),
        "truth_layer": str(payload.get("truth_layer") or "preview"),
    }


def _read_draft_files(directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        payload = _read_json(path)
        if isinstance(payload, Mapping) and payload.get("draft_id"):
            rows.append(dict(payload))
    return rows


def read_writer_drafts(project_root: Path | str, novel_id: str, *,
                       writer_dir: str = WRITER_DIR) -> list[dict[str, Any]]:
    """唯一的 writer 草稿读取入口（投影 / 导出 / 列表都走这里）。

    顺序：

    1. canonical `index.json`（写入方始终维护）；
    2. canonical `drafts/*.json`（索引缺失时按真实文件重建，不写盘）；
    3. legacy `workspace/wasteland_001_exports/writer_v1`（**只读兼容**，仅当
       canonical 完全没有草稿时才使用，避免同一份草稿被计两次）。
    """

    payload = _read_json(writer_index_path(project_root, novel_id, writer_dir=writer_dir))
    if isinstance(payload, Mapping):
        drafts = payload.get("drafts")
        if isinstance(drafts, list) and drafts:
            return [dict(row) for row in drafts if isinstance(row, Mapping)]
    elif isinstance(payload, list) and payload:
        return [dict(row) for row in payload if isinstance(row, Mapping)]

    store = writer_store_path(project_root, novel_id, writer_dir=writer_dir)
    rows = [draft_summary(item) for item in _read_draft_files(store / "drafts")]
    if rows:
        return sorted(rows, key=lambda row: str(row.get("generated_at") or ""), reverse=True)

    legacy = writer_store_path(project_root, novel_id, writer_dir=LEGACY_WRITER_STORE_DIR)
    rows = [draft_summary(item) for item in _read_draft_files(legacy / "drafts")]
    return sorted(rows, key=lambda row: str(row.get("generated_at") or ""), reverse=True)


class WriterContextBuilder:
    """M16B：把各层事实/规划收敛成分层 writer context（单一入口）。"""

    def __init__(self, project_root: Path | str, novel_id: str) -> None:
        self.root = Path(project_root).resolve()
        self.novel_id = novel_id

    # ------------------------------------------------------------ blocks
    def _canon_block(self) -> dict[str, Any]:
        from novelforge.story_engine.canon.repository import CanonRepository

        db = self.root / CANON_DB
        items: list[dict[str, Any]] = []
        if db.is_file():
            repository = CanonRepository(db)
            try:
                for row in repository.facts(self.novel_id)[:BLOCK_BUDGET]:
                    items.append({"id": row.fact_id, "kind": row.category,
                                  "text": row.canonical_description or row.canonical_key,
                                  "status": row.status})
            finally:
                repository.close()
        return {"source": CANON_DB, "identity": self.novel_id, "items": items}

    def _state_block(self, context: Any, package: Mapping[str, Any],
                     card_id: str) -> dict[str, Any]:
        world = world_snapshot(context)
        items: list[dict[str, Any]] = [
            {"id": "runtime", "kind": "summary",
             "text": f"tick {world['timeline']['tick']} · {world['timeline']['current_time']} · "
                     f"地点 {world['location']['name'] or world['location']['current']}"},
            *[{"id": row["id"], "kind": "character", "text": row["name"]}
              for row in world.get("characters") or []],
            *[{"id": row["id"], "kind": "location", "text": row.get("name") or row["id"]}
              for row in world["location"]["known"]],
        ]
        memory = memory_snapshot(context)
        items.extend({"id": row["id"], "kind": "knowledge",
                      "text": f"{row['id']}（{row['certainty']}）"}
                     for row in (memory.get("knowledge_index") or [])[:10])
        return {"source": "StoryState（runtime）",
                "identity": card_id or context.runtime_id or self.novel_id,
                "items": items}

    def _repair_block(self, chapter_id: str) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        store = HistoricalIRStore(_history_dir(self.root))
        if (_history_dir(self.root) / "index.json").is_file() and chapter_id:
            artifacts = store.load_artifacts()
            artifact = artifacts.get(chapter_id)
            if artifact is not None:
                items.append({
                    "id": artifact.chapter_id, "kind": "historical_ir_chapter",
                    "text": f"{artifact.legacy_label}｜{artifact.chapter_function}｜"
                            f"{artifact.materialization_status}",
                    "source_ref": f"{HISTORY_DIR}/artifacts/{artifact.chapter_id}.json"})
        items.append({"id": "repair_replay", "kind": "artifact_ref",
                      "text": f"{HISTORY_DIR}/REPAIR_REPLAY.json"})
        items.append({"id": "reconciliation", "kind": "artifact_ref",
                      "text": "M11_FINAL_CLOSURE_RECONCILIATION.json"})
        return {"source": HISTORY_DIR,
                "identity": chapter_id or "historical_foundation", "items": items}

    def _planning_block(self) -> dict[str, Any]:
        chain = load_forge_chain(self.root, self.novel_id, branch_id=DEFAULT_BRANCH)
        items: list[dict[str, Any]] = []
        for package in [chain["book"], *chain["volumes"], *chain["arcs"]]:
            if package is None:
                continue
            for item in package.items[:5]:
                items.append({"id": item.item_id, "kind": package.level.value.lower(),
                              "text": f"{item.title}：{item.summary}"})
        return {"source": "outline_forge.load_forge_chain",
                "identity": DEFAULT_BRANCH, "items": items[:BLOCK_BUDGET]}

    def _chapter_plan_block(self, chapter_id: str, plan: Mapping[str, Any]
                            ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        if plan:
            items.append({"id": "chapter_plan", "kind": "chapter",
                          "text": f"{plan.get('title')}｜目标：{plan.get('goal')}｜"
                                  f"冲突：{plan.get('conflict')}｜转折：{plan.get('turn')}｜"
                                  f"钩子：{plan.get('hook')}"})
            items.extend({"id": f"info_{index}", "kind": "information",
                          "text": str(text)}
                         for index, text in enumerate(plan.get("information_changes") or [],
                                                      start=1))
        return {"source": "outline chapter plan（planned）",
                "identity": chapter_id or "", "items": items}

    def _guidance_block(self, package: Mapping[str, Any]) -> dict[str, Any]:
        items: list[dict[str, Any]] = [
            *[{"id": f"required_{index}", "kind": "required_result", "text": str(text)}
              for index, text in enumerate(package.get("required_results") or [], start=1)],
            *[{"id": f"forbidden_{index}", "kind": "forbidden", "text": str(text)}
              for index, text in enumerate(package.get("forbidden") or [], start=1)],
            *[{"id": f"space_{index}", "kind": "creative_space", "text": str(text)}
              for index, text in enumerate(package.get("creative_space") or [], start=1)],
        ]
        return {"source": "WriterPackage（writer-only guidance）",
                "identity": package.get("event_id") or "writer_guidance", "items": items}

    # ------------------------------------------------------------ build
    def build(self, *, branch_id: str = DEFAULT_BRANCH, chapter_id: str = "",
              event_id: str = "") -> dict[str, Any]:
        context = resolve_creator_context(self.root, self.novel_id)
        state = context.state
        card = next((item for item in (state.active_events + state.resolved_events)
                     if item.id == event_id), None) if event_id else None
        package = build_writer_package(state, card).as_dict()
        pack_id = saved_pack_id(self.root, self.novel_id)
        pack = load_pack_draft(self.root, pack_id) if pack_id else context.pack
        plan: dict[str, Any] = {}
        if chapter_id:
            chain = load_forge_chain(self.root, self.novel_id, branch_id=branch_id)
            for source in [chain["chapters"], chain["arcs"], chain["volumes"],
                           [chain["book"]]]:
                for item in source or []:
                    if item is None:
                        continue
                    if item.package_id == chapter_id or any(
                            row.item_id == chapter_id for row in item.items):
                        target = next((row for row in item.items
                                       if row.item_id == chapter_id), item.items[0])
                        plan = {"title": target.title, "goal": target.summary,
                                "conflict": "；".join(target.conflicts),
                                "turn": "；".join(target.major_turns),
                                "hook": target.ending_hook,
                                "information_changes": list(target.information_changes)}
                        break
        raw_blocks = {
            "canon_truth": self._canon_block(),
            "story_state": self._state_block(context, package, chapter_id),
            "historical_repair": self._repair_block(chapter_id),
            "planning": self._planning_block(),
            "chapter_plan": self._chapter_plan_block(chapter_id, plan),
            "writer_guidance": self._guidance_block(package),
        }
        seen: dict[str, str] = {}
        deduplicated: list[dict[str, str]] = []
        blocks: list[dict[str, Any]] = []
        for block_id, truth_layer, priority in TRUTH_BLOCKS:
            raw = raw_blocks[block_id]
            kept: list[dict[str, Any]] = []
            dropped = 0
            for item in raw["items"]:
                key = str(item.get("id") or item.get("text"))
                if key in seen:
                    deduplicated.append({"item": key, "kept_block": seen[key],
                                         "dropped_block": block_id})
                    continue
                if len(kept) >= BLOCK_BUDGET:
                    dropped += 1
                    continue
                seen[key] = block_id
                kept.append(dict(item))
            kept.sort(key=lambda row: (str(row.get("kind") or ""), str(row.get("id") or "")))
            blocks.append({
                "block_id": block_id, "truth_layer": truth_layer, "priority": priority,
                "source": raw["source"], "identity": raw["identity"],
                "item_count": len(kept), "dropped_count": dropped,
                "digest": _digest(kept), "items": kept})
        payload = {
            "context_id": f"writer_ctx_{self.novel_id}_"
                          f"{_digest([row['digest'] for row in blocks])}",
            "format_version": CONTEXT_FORMAT_VERSION,
            "novel_id": self.novel_id, "branch_id": branch_id,
            "chapter_id": chapter_id, "event_id": event_id,
            "pack_id": pack_id,
            "blocks": blocks,
            "block_order": [row["block_id"] for row in blocks],
            "deduplicated": deduplicated,
            "budget": {"max_items_per_block": BLOCK_BUDGET},
            "writer_package": package,
            "truth_layer_legend": {
                "occurred": "Canon / StoryState（已发生事实，不得改写）",
                "historical_repair": "M11/M12 frozen repair evidence（只读）",
                "planned": "规划 / 章节计划（未提交为事实）",
                "ui_derived": "writer-only guidance（不成为事实）"},
            "preview_only": True,
            "read_only": True, "non_authoritative": True,
        }
        payload["validation"] = validate_writer_context(payload)
        return payload


def validate_writer_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """M16B validation：truth separation / 无重复 ownership / 稳定顺序 / 完整性。"""

    blocks = list(context.get("blocks") or [])
    by_id = {row["block_id"]: row for row in blocks}
    truth_by_block = {block_id: layer for block_id, layer, _ in TRUTH_BLOCKS}
    ownership: dict[str, str] = {}
    duplicate_ownership: list[str] = []
    for row in blocks:
        for item in row["items"]:
            key = str(item.get("id") or item.get("text"))
            if key in ownership:
                duplicate_ownership.append(key)
            ownership[key] = row["block_id"]
    ordered = [row["block_id"] for row in blocks]
    checks = {
        "truth_layer_matches_declaration": all(
            row["truth_layer"] == truth_by_block.get(row["block_id"]) for row in blocks),
        "required_blocks_present": {"canon_truth", "story_state", "historical_repair",
                                    "planning", "chapter_plan",
                                    "writer_guidance"} <= set(by_id),
        "no_duplicate_ownership": not duplicate_ownership,
        "stable_block_order": ordered == [block_id for block_id, _, _ in TRUTH_BLOCKS],
        "planned_not_in_occurred": not any(
            str(item.get("kind")) == "chapter" for item in
            by_id["story_state"]["items"]),
        "story_state_present": bool(by_id["story_state"]["items"]),
        "writer_guidance_present": bool(by_id["writer_guidance"]["items"]),
        "preview_only": bool(context.get("preview_only")),
    }
    return {"validation_id": "M16B_WRITER_CONTEXT_VALIDATION",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "duplicate_ownership": duplicate_ownership,
            "block_count": len(blocks),
            "read_only": True, "non_authoritative": True}


class WriterDraftService:
    """M16B：writer 产品入口 + draft 存储 + Draft Fact Sync（只产生 proposal）。"""

    def __init__(self, project_root: Path | str, novel_id: str,
                 *, writer_dir: str = WRITER_DIR) -> None:
        self.root = Path(project_root).resolve()
        self.novel_id = novel_id
        self.writer_dir = writer_dir
        self.dir = self.root / writer_dir / novel_id
        self.builder = WriterContextBuilder(self.root, novel_id)

    # ------------------------------------------------------------ drafts
    def _index_path(self) -> Path:
        return self.dir / "index.json"

    def _refresh_index(self) -> list[dict[str, Any]]:
        """把草稿目录的真实状态写回 index.json（列表页的唯一读取入口）。"""

        rows = [draft_summary(item) for item in _read_draft_files(self.dir / "drafts")]
        rows.sort(key=lambda row: str(row.get("generated_at") or ""), reverse=True)
        _write_json(self._index_path(), {
            "novel_id": self.novel_id,
            "updated_at": _now(),
            "canonical_dir": f"{self.writer_dir}/{self.novel_id}",
            "draft_count": len(rows),
            "drafts": rows,
            "truth_layer": "preview",
            "read_only": True, "non_authoritative": True,
        })
        return rows

    def create_draft(self, *, branch_id: str = DEFAULT_BRANCH, chapter_id: str = "",
                     event_id: str = "", claims: Sequence[Mapping[str, Any]] = (),
                     new_facts: Sequence[Mapping[str, Any]] = (),
                     narration: str = "", style: Mapping[str, str] | None = None
                     ) -> dict[str, Any]:
        context = self.builder.build(branch_id=branch_id, chapter_id=chapter_id,
                                     event_id=event_id)
        creator_context = resolve_creator_context(self.root, self.novel_id)
        state = creator_context.state
        card = next((item for item in (state.active_events + state.resolved_events)
                     if item.id == event_id), None) if event_id else None
        package = build_writer_package(state, card, style=dict(style) if style else None)
        text = narration or render_scene(state, package) if event_id else (
            narration or fallback_text(package))
        output = WriterOutput(
            narration=text,
            claims=[WriterClaim(**dict(row)) for row in claims],
            proposed_new_facts=[dict(row) for row in new_facts])
        validation = validate_writer_output(state, package, output)
        draft_seed = _digest([context["context_id"], text,
                              [dict(row) for row in claims],
                              [dict(row) for row in new_facts]])
        draft_id = f"draft_{chapter_id or event_id or 'overview'}_{draft_seed}"
        payload = {
            "generated_at": _now(), "draft_id": draft_id,
            "novel_id": self.novel_id, "branch_id": branch_id,
            "chapter_id": chapter_id, "event_id": event_id,
            "context_id": context["context_id"],
            "context_validation": context["validation"],
            "narration": text,
            "claims": [dict(row) for row in claims],
            "proposed_new_facts": list(output.proposed_new_facts),
            "validation": validation.as_dict(),
            "truth_layer": "preview",
            "fact_sync": {"synced": False, "proposal_count": 0},
            "note": ("writer 输出属于 preview 层：不写 StoryState / Canon；"
                     "Draft Fact Sync 只产生 proposal，需作者 / 修复流程确认"),
            "read_only": True, "non_authoritative": True,
        }
        _write_json(self.dir / "drafts" / f"{draft_id}.json", payload)
        # 写入路径与投影读取路径同源：写完草稿立刻维护 canonical index。
        self._refresh_index()
        return payload

    def list_drafts(self) -> list[dict[str, Any]]:
        return read_writer_drafts(self.root, self.novel_id, writer_dir=self.writer_dir)

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        path = self.dir / "drafts" / f"{draft_id}.json"
        payload = _read_json(path)
        if not payload:
            return {"draft_id": draft_id, "found": False,
                    "note": "草稿不存在", "read_only": True}
        return {**payload, "found": True}

    # ------------------------------------------------------------ fact sync
    def sync_facts(self, draft_id: str) -> dict[str, Any]:
        """Draft Fact Sync：writer 声明 → proposal（不写事实）。"""

        draft = self.get_draft(draft_id)
        if not draft.get("found"):
            return {"draft_id": draft_id, "status": "NOT_FOUND",
                    "proposals": [], "read_only": True}
        state_before = _digest(resolve_creator_context(
            self.root, self.novel_id).state.model_dump(mode="json"))
        proposals: list[dict[str, Any]] = []
        for index, claim in enumerate(draft.get("claims") or [], start=1):
            proposals.append({
                "proposal_id": f"WFP_{draft_id}_{index:02d}",
                "source_draft": draft_id,
                "kind": claim.get("kind"), "id": claim.get("id"),
                "holder": claim.get("holder"), "value": claim.get("value"),
                "note": claim.get("note", ""),
                "status": "PROPOSED",
                "truth_layer": "planned",
                "requires_approval": True,
                "approval_boundary": ("作者确认或走 Repair Center / M11 repair 正式流程；"
                                      "NovelForge 不自动写入"),
                "evidence": [f"{draft_id}#claim{index}"],
            })
        for index, proposal in enumerate(draft.get("proposed_new_facts") or [], start=1):
            proposals.append({
                "proposal_id": f"WFP_{draft_id}_nf{index:02d}",
                "source_draft": draft_id, "kind": "persistent_fact",
                "id": str(proposal.get("character_id") or ""),
                "holder": str(proposal.get("character_id") or ""),
                "value": proposal.get("detail"), "note": "长期人物事实提议",
                "status": "PROPOSED", "truth_layer": "planned",
                "requires_approval": True,
                "approval_boundary": "长期人物事实必须由作者确认后才能进入 Canon",
                "evidence": [f"{draft_id}#new_fact{index}"],
            })
        payload = {
            "generated_at": _now(), "draft_id": draft_id,
            "status": "SYNCED" if proposals else "NOTHING_TO_SYNC",
            "proposal_count": len(proposals), "proposals": proposals,
            "truth_layer": "planned",
            "wrote_story_state": False, "wrote_canon": False,
            "boundary": ("Draft Fact Sync 只把 writer 声明转成 proposal；"
                         "StoryState / Canon 保持不变"),
            "read_only": True, "non_authoritative": True,
        }
        _write_json(self.dir / "proposals" / f"{draft_id}_proposals.json", payload)
        stored = self.get_draft(draft_id)
        stored["fact_sync"] = {"synced": True, "proposal_count": len(proposals),
                               "proposal_ref": f"proposals/{draft_id}_proposals.json"}
        _write_json(self.dir / "drafts" / f"{draft_id}.json", stored)
        self._refresh_index()
        payload["state_unchanged"] = state_before == _digest(resolve_creator_context(
            self.root, self.novel_id).state.model_dump(mode="json"))
        return payload


def writer_export_bundle(project_root: Path | str, novel_id: str, *,
                         branch_id: str = DEFAULT_BRANCH) -> dict[str, Any]:
    """Writer-ready Package：export projection + 分层 writer context 的联合入口。"""

    from novelforge.story_builder.export_package import build_export_projection

    projection = build_export_projection(project_root, novel_id, branch_id=branch_id)
    context = WriterContextBuilder(project_root, novel_id).build(branch_id=branch_id)
    return {
        "novel_id": novel_id, "branch_id": branch_id,
        "export_manifest": projection["manifest"],
        "writer_context_id": context["context_id"],
        "writer_context_validation": context["validation"],
        "blocks": [{"block_id": row["block_id"], "truth_layer": row["truth_layer"],
                    "item_count": row["item_count"]} for row in context["blocks"]],
        "preview_only": True, "read_only": True, "non_authoritative": True,
    }


__all__ = [
    "BLOCK_BUDGET", "CONTEXT_FORMAT_VERSION", "LEGACY_WRITER_STORE_DIR", "TRUTH_BLOCKS",
    "WRITER_DIR", "WRITER_STORE_DIR", "WriterContextBuilder", "WriterDraftService",
    "draft_summary", "read_writer_drafts", "validate_writer_context",
    "writer_export_bundle", "writer_index_path", "writer_store_path",
]
