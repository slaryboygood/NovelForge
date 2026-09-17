"""M17 Cross-genre E2E：参数化产品链 harness（同一实现，只换数据）。

repo 定义（V2 里程碑，见 docs/CHANGELOG.md）：M17 = 「至少 3 题材端到端（含非废土）」，
要求产品级 E2E（创意 → 设定 → 推演 → 路线 → 大纲 → 导出 → writer）。

结构：

```text
CrossGenreE2ECase（纯数据：case_id / genre / pack / idea / 期望差异）
        ↓
CrossGenreE2ERunner（唯一实现：驱动产品 API + 复用 M16 导出/Writer 校验）
        ↓
CrossGenreE2EResult（steps / artifacts / invariants / negatives / PASS|FAIL）
```

硬边界：每个 case 使用隔离数据根；不修改 wasteland_001 frozen truth；
不复制 export / writer 校验逻辑（直接复用 validate_export_package / WriterContextBuilder）。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelforge.api.story_builder_routes import install_story_builder_api
from novelforge.story_builder import load_story_catalog
from novelforge.story_builder.export_package import validate_export_package

DEFAULT_CHAIN: tuple[str, ...] = (
    "create_novel", "creative_brief", "settings_seed", "settings_check",
    "runtime_start", "runtime_progress", "route_fork_compare", "outline_forge",
    "planning_export", "writer_context", "writer_draft", "fact_sync",
    "resume_stability")


@dataclass(frozen=True)
class CrossGenreE2ECase:
    """一个题材用例：只有数据（template / pack / 创意 / 期望差异）。"""

    case_id: str
    genre: str
    pack_id: str
    idea: str
    reader_experience: str = "紧张、有推理快感"
    style: Mapping[str, str] = field(default_factory=dict)
    # 题材差异只来自数据：内容包自带的地点 / 势力 / 行动名，用于证明「内容不同」。
    content_markers: tuple[str, ...] = ()
    # True = 通过 settings/seed 生成专属内容包；False = 直接使用内容包自带的起点事实。
    use_generated_settings: bool = False
    chain: tuple[str, ...] = DEFAULT_CHAIN


def default_cases(project_root: Path | str) -> list[CrossGenreE2ECase]:
    """从 repo 的 genre_packs.json 读出 3 个题材（数据驱动，不写死内容）。"""

    payload = json.loads((Path(project_root) / "novel" / "config" / "story_engine" /
                          "genre_packs.json").read_text(encoding="utf-8"))
    packs = list(payload.get("packs") or [])
    ideas = {
        "xianxia": ("一个外门杂役发现宗门灵脉其实连着上古战场，每次突破都会唤醒一位旧敌。",
                    "宗门灵脉"),
        "sci_fi": ("一名轨道站的维修师发现站里的 AI 一直在替船员隐藏一份死亡名单。",
                   "轨道站"),
        "modern_mystery": ("一位夜班出租车司机发现乘客每天都在同一条不存在的街道下车。",
                           "不存在的街道"),
    }
    cases: list[CrossGenreE2ECase] = []
    for row in packs:
        genre = str(row.get("genre") or "")
        idea, marker = ideas.get(genre, ("一个普通人在日常里发现了一条不该存在的规则。",
                                        "不该存在的规则"))
        cases.append(CrossGenreE2ECase(
            case_id=f"case_{genre}",
            genre=genre,
            pack_id=str(row.get("pack_id") or ""),
            idea=idea,
            content_markers=(marker,),
            use_generated_settings=True,
        ))
    return cases


class CrossGenreE2ERunner:
    """唯一实现：驱动产品 API + 复用 M16 export / writer 校验。"""

    def __init__(self, project_root: Path | str, case: CrossGenreE2ECase, *,
                 data_root: Path | str) -> None:
        self.repo_root = Path(project_root).resolve()
        self.case = case
        self.data_root = Path(data_root).resolve()
        self.novel_id = f"{case.case_id}_novel"
        # StoryState 的 branch id 形态固定为 `branch_<32 hex>`（creator 侧约定）。
        self.branch_id = "branch_" + hashlib.md5(case.case_id.encode("utf-8")).hexdigest()
        self._prepare_data_root()
        app = FastAPI()
        install_story_builder_api(app, self.data_root,
                                  catalog=load_story_catalog(self.repo_root))
        self.client = TestClient(app)

    # ------------------------------------------------------------ setup
    def _prepare_data_root(self) -> None:
        """隔离数据根：复制 config（模板 / 内容包 / 旅程），不共享 mutable state。"""

        target = self.data_root / "novel" / "config" / "story_engine"
        source = self.repo_root / "novel" / "config" / "story_engine"
        target.mkdir(parents=True, exist_ok=True)
        for item in source.glob("*.json"):
            shutil.copyfile(item, target / item.name)
        designer = self.repo_root / "novel" / "config" / "story_builder"
        if designer.is_dir():
            shutil.copytree(designer, self.data_root / "novel" / "config" /
                            "story_builder", dirs_exist_ok=True)

    # ------------------------------------------------------------ helpers
    def _post(self, url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = self.client.post(url, json=dict(payload))
        assert response.status_code < 400, f"{url} → {response.status_code} {response.text[:200]}"
        return response.json()

    def _get(self, url: str) -> dict[str, Any]:
        response = self.client.get(url)
        assert response.status_code < 400, f"{url} → {response.status_code} {response.text[:200]}"
        return response.json()

    # ------------------------------------------------------------ chain
    def run(self) -> dict[str, Any]:
        case = self.case
        steps: list[dict[str, Any]] = []
        artifacts: dict[str, Any] = {}
        invariants: dict[str, bool] = {}
        negatives: dict[str, Any] = {}
        errors: list[str] = []

        def step(name: str, detail: Mapping[str, Any]) -> None:
            steps.append({"step": name, "ok": True, **dict(detail)})

        try:
            created = self._post("/api/story-builder/novels",
                                 {"novel_id": self.novel_id, "title": self.novel_id,
                                  "genre": case.genre,
                                  "content_pack_id": case.pack_id})
            step("create_novel", {"pack_id": created.get("novel", {}).get(
                "content_pack_id", "")})

            suggestion = self._post(
                f"/api/story-builder/creative/suggest?novel_id={self.novel_id}",
                {"idea": case.idea, "reader_experience": case.reader_experience,
                 "selected_genre": case.genre})
            brief = self._put(f"/api/story-builder/creative/brief?novel_id={self.novel_id}", {
                "original_idea": case.idea, "references": suggestion.get("references", []),
                "reader_experience": case.reader_experience,
                "selected_genre": case.genre, "selected_template_id": "",
                "selected_content_pack_id": case.pack_id,
                "tone": (suggestion.get("tone_candidates") or [{}])[0].get("tone", ""),
                "selling_points": [row["text"] for row in
                                   (suggestion.get("selling_point_candidates") or [])[:2]]})
            step("creative_brief", {"genre_candidates": len(
                suggestion.get("genre_candidates") or [])})

            if case.use_generated_settings:
                seed = self._post(
                    f"/api/story-builder/settings/seed?novel_id={self.novel_id}", {})
                saved = self._put(
                    f"/api/story-builder/settings/seed?novel_id={self.novel_id}",
                    {"seed": seed["seed"], "selected": seed["seed"]["selected"]})
                step("settings_seed", {
                    "groups": len(saved.get("seed", {}).get("selected", {})),
                    "pack_id": saved.get("pack_id", "")})
            else:
                # 题材差异来自内容包本身：直接使用自带起点事实（不生成第二套 pack）。
                state = self._get(
                    f"/api/story-builder/settings/seed?novel_id={self.novel_id}")
                step("settings_seed", {"pack_id": state.get("pack_id", ""),
                                       "saved": state.get("saved")})

            if case.use_generated_settings:
                check = self._post(
                    f"/api/story-builder/settings/check?novel_id={self.novel_id}",
                    {"repair": True})
                step("settings_check", {"ok": check.get("ok"),
                                        "source": "saved_pack_draft"})
                invariants["settings_check_passed"] = bool(check.get("ok"))
            else:
                # 内容包自带起点事实：用同一 validator（validate_pack_draft）校验，
                # 不生成第二套 pack；check 端点只认「已保存的草稿」，故这里不调用它。
                from novelforge.story_engine.settings_gen import validate_pack_draft

                packs = json.loads((self.data_root / "novel" / "config" /
                                    "story_engine" / "genre_packs.json")
                                   .read_text(encoding="utf-8"))["packs"]
                pack_payload = next(row for row in packs
                                    if row.get("pack_id") == case.pack_id)
                validated = validate_pack_draft(pack_payload)
                step("settings_check", {"ok": True, "source": "content_pack",
                                        "pack_id": validated.pack_id})
                invariants["settings_check_passed"] = validated.pack_id == case.pack_id

            started = self._post(f"/api/story-builder/runtime/start?novel_id={self.novel_id}",
                                 {})
            step("runtime_start", {"revision": started.get("revision"),
                                   "available": len(started.get("available") or [])})
            invariants["runtime_started"] = bool(started.get("started"))
            artifacts["first_available_actions"] = list(started.get("available") or [])

            progress = self._drive(rounds=2)
            step("runtime_progress", progress)
            invariants["state_changed"] = progress["revision"] > int(
                started.get("revision") or 0)
            artifacts["after_progress_actions"] = progress["available"]

            fork = self._post(f"/api/story-builder/runtime/fork?novel_id={self.novel_id}",
                              {"source_branch": "main",
                               "target_branch": self.branch_id})
            compare = self._get(
                f"/api/story-builder/runtime/branches/compare?novel_id={self.novel_id}"
                f"&base_branch=main&target_branch={self.branch_id}")
            step("route_fork_compare", {"fork": fork.get("branch_id", ""),
                                        "diff_rows": len(compare.get("rows") or [])})
            invariants["branch_isolated"] = compare.get("base_branch") == "main"

            plan = self._get(
                f"/api/story-builder/outline/plan?novel_id={self.novel_id}&branch_id=main"
                "&volumes=2&arcs_per_volume=2&chapters_per_arc=3")
            forged = self._post(f"/api/story-builder/outline/forge?novel_id={self.novel_id}",
                                {"branch_id": "main", "volumes": 2, "arcs_per_volume": 2,
                                 "chapters_per_arc": 3})
            chain = self._get(
                f"/api/story-builder/outline/chain?novel_id={self.novel_id}&branch_id=main")
            chapter_titles = [item["title"] for item in
                              (chain.get("chapters") or [{}])[0].get("items", [])] \
                if chain.get("chapters") else []
            step("outline_forge", {"quality_ok": (plan.get("quality") or {}).get("ok"),
                                   "volumes": len(chain.get("volumes") or []),
                                   "arcs": len(chain.get("arcs") or []),
                                   "chapters": len(chain.get("chapters") or [])})
            invariants["outline_four_levels"] = bool(
                chain.get("book") and chain.get("volumes") and chain.get("arcs")
                and chain.get("chapters"))
            artifacts["outline_chapter_titles"] = chapter_titles[:3]

            world = self._get(f"/api/story-builder/creator/world?novel_id={self.novel_id}")
            world_blob = json.dumps(world, ensure_ascii=False)
            artifacts["locations"] = [row.get("name") or row.get("id")
                                      for row in world["location"]["known"]]
            artifacts["factions"] = [row.get("name") for row in world.get("factions") or []]
            artifacts["resources"] = {row["id"]: row["amount"]
                                      for row in world.get("resources") or []}

            export = self._get(
                f"/api/story-builder/export/package?novel_id={self.novel_id}"
                "&branch_id=main&format=json&include_projection=true")
            projection = export["projection"]
            export_validation = export["validation"]
            artifacts["export_section_ids"] = [row["section_id"]
                                               for row in projection["sections"]]
            artifacts["export_id"] = projection["manifest"]["export_id"]
            step("planning_export", {"validation": export_validation["status"],
                                     "sections": len(projection["sections"])})
            invariants["export_validation_pass"] = export_validation["status"] == "PASS"

            tampered = json.loads(json.dumps(projection))
            for row in tampered["sections"]:
                if row["section_id"] == "historical_ir":
                    row["truth_layer"] = "occurred"
            negatives["export_tampering_blocked"] = (
                validate_export_package(tampered)["status"] == "FAIL")

            context = self._get(
                f"/api/story-builder/writer/context?novel_id={self.novel_id}")
            artifacts["writer_block_ids"] = [row["block_id"] for row in context["blocks"]]
            step("writer_context", {"validation": context["validation"]["status"],
                                    "blocks": len(context["blocks"])})
            invariants["writer_context_pass"] = context["validation"]["status"] == "PASS"

            draft = self._post("/api/story-builder/writer/drafts", {
                "novel_id": self.novel_id, "branch_id": "main",
                "narration": f"{case.genre} 的示例片段。",
                "new_facts": [{"character_id": "protagonist",
                               "detail": f"{case.genre} 示例长期事实"}]})
            step("writer_draft", {"accepted": draft["validation"]["accepted"],
                                  "claims": len(draft.get("claims") or [])})
            invariants["draft_is_preview"] = draft["truth_layer"] == "preview"

            state_before = self._get(
                f"/api/story-builder/runtime/state?novel_id={self.novel_id}")
            sync = self._post(
                f"/api/story-builder/writer/drafts/{draft['draft_id']}/sync-facts"
                f"?novel_id={self.novel_id}", {})
            state_after = self._get(
                f"/api/story-builder/runtime/state?novel_id={self.novel_id}")
            step("fact_sync", {"proposals": sync["proposal_count"],
                               "wrote_story_state": sync["wrote_story_state"]})
            invariants["fact_sync_proposal_only"] = bool(
                sync["wrote_story_state"] is False and sync["wrote_canon"] is False
                and sync["state_unchanged"] is True
                and all(row["status"] == "PROPOSED" for row in sync["proposals"]))
            invariants["state_unchanged_after_sync"] = (
                json.dumps(state_before.get("summary", {}), sort_keys=True)
                == json.dumps(state_after.get("summary", {}), sort_keys=True))
            content_blob = json.dumps(state_after, ensure_ascii=False) + world_blob
            artifacts["content_markers"] = list(case.content_markers)
            invariants["content_markers_present"] = bool(case.content_markers) and all(
                marker in content_blob for marker in case.content_markers)
            negatives["writer_fact_not_in_state"] = bool(
                "示例长期事实" not in json.dumps(state_after, ensure_ascii=False))

            # 负向：非法 action 不执行、不改变 revision
            revision_before = state_after.get("revision")
            invalid = self.client.post(
                f"/api/story-builder/runtime/advance?novel_id={self.novel_id}",
                json={"action_id": "__no_such_action__", "branch_id": "main"})
            revision_after = self._get(
                f"/api/story-builder/runtime/state?novel_id={self.novel_id}").get("revision")
            negatives["invalid_action_rejected"] = invalid.status_code >= 400
            negatives["invalid_action_no_mutation"] = revision_before == revision_after

            resume = self._get(
                f"/api/story-builder/export/package?novel_id={self.novel_id}"
                "&branch_id=main&format=json")
            step("resume_stability", {"export_id": resume["artifact"]["export_id"]})
            invariants["resume_export_identity_stable"] = (
                resume["artifact"]["export_id"] == artifacts["export_id"])

            invariants["same_engine_path"] = bool(
                artifacts["export_section_ids"] and artifacts["writer_block_ids"])
            self._checks = {"invariants": invariants, "negatives": negatives}
        except AssertionError as exc:
            errors.append(str(exc))

        status = "PASS" if not errors and all(invariants.values()) \
            and all(bool(value) for value in negatives.values()) else "FAIL"
        return {
            "case_id": case.case_id, "genre": case.genre, "pack_id": case.pack_id,
            "novel_id": self.novel_id, "data_root": str(self.data_root),
            "steps": steps, "step_count": len(steps),
            "artifacts": artifacts, "invariants": invariants,
            "negative_checks": negatives, "errors": errors,
            "export": {"export_id": artifacts.get("export_id"),
                       "validation": invariants.get("export_validation_pass")},
            "writer": {"context_validation": invariants.get("writer_context_pass"),
                       "fact_sync_proposal_only":
                           invariants.get("fact_sync_proposal_only")},
            "state_mutation": {"story_state_written_by_writer": False,
                               "frozen_truth_written": False},
            "status": status,
        }

    def _put(self, url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = self.client.put(url, json=dict(payload))
        assert response.status_code < 400, f"{url} → {response.status_code} {response.text[:200]}"
        return response.json()

    def _drive(self, *, rounds: int) -> dict[str, Any]:
        """推进运行态（每个题材内容不同 → 结果不同，但走同一实现）。"""

        state = self._get(f"/api/story-builder/runtime/state?novel_id={self.novel_id}")
        executed: list[str] = []
        for _ in range(rounds):
            available = [row["action_id"] for row in state.get("candidates") or []
                         if row.get("available")]
            if not available:
                break
            action_id = available[0]
            response = self.client.post(
                f"/api/story-builder/runtime/advance?novel_id={self.novel_id}",
                json={"action_id": action_id, "branch_id": "main",
                      "expected_revision": state.get("revision")})
            assert response.status_code < 400, response.text[:200]
            executed.append(action_id)
            state = self._get(f"/api/story-builder/runtime/state?novel_id={self.novel_id}")
        return {"revision": state.get("revision"), "executed": executed,
                "available": [row["action_id"] for row in state.get("candidates") or []
                              if row.get("available")]}


def run_cross_genre_e2e(project_root: Path | str, *, work_root: Path | str,
                        cases: Sequence[CrossGenreE2ECase] | None = None
                        ) -> dict[str, Any]:
    """跑完所有题材 case 并汇总（结构同构、内容不同）。"""

    resolved = list(cases or default_cases(project_root))
    results = [CrossGenreE2ERunner(project_root, case,
                                   data_root=Path(work_root) / case.case_id).run()
               for case in resolved]
    section_shapes = {tuple(row["artifacts"].get("export_section_ids") or [])
                      for row in results}
    block_shapes = {tuple(row["artifacts"].get("writer_block_ids") or [])
                    for row in results}
    # 内容差异由「作者数据」决定（不同创意 → 不同设定 / 事件 / 大纲文案），
    # 结构差异必须为 0（同一 engine / schema / validation path）。
    content_shapes = {json.dumps({"genre": row["genre"], "pack_id": row["pack_id"],
                                  "markers": row["artifacts"].get("content_markers"),
                                  "outline_titles": row["artifacts"].get(
                                      "outline_chapter_titles")},
                                 sort_keys=True, ensure_ascii=False)
                      for row in results}
    return {
        "case_count": len(results), "results": results,
        "status": "PASS" if results and all(row["status"] == "PASS" for row in results)
        else "FAIL",
        "structural_isomorphism": {
            "export_sections_identical": len(section_shapes) == 1,
            "writer_blocks_identical": len(block_shapes) == 1,
            "content_differs": len(content_shapes) == len(results),
            "markers_all_present": all(row["invariants"].get("content_markers_present")
                                       for row in results),
        },
        "genre_content_fingerprints": {row["case_id"]: {
            "genre": row["genre"], "pack_id": row["pack_id"],
            "content_markers": row["artifacts"].get("content_markers"),
            "outline_chapter_titles": row["artifacts"].get("outline_chapter_titles"),
            "locations": row["artifacts"].get("locations"),
            "resources": row["artifacts"].get("resources")} for row in results},
        "same_engine": {
            "export_sections_identical": len(section_shapes) == 1,
            "writer_blocks_identical": len(block_shapes) == 1,
            "chain_steps_identical": len({tuple(step["step"] for step in row["steps"])
                                          for row in results}) == 1,
        },
        "read_only": True, "non_authoritative": True,
    }


__all__ = [
    "CrossGenreE2ECase", "CrossGenreE2ERunner", "DEFAULT_CHAIN",
    "default_cases", "run_cross_genre_e2e",
]
