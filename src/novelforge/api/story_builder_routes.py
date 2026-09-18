from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from novelforge.story_builder.adventures import AdventureEngine
from novelforge.story_builder.design_tree import design_view, save_design
from novelforge.story_engine import (
    DEFAULT_NOVEL_ID,
    CreatorContextError,
    GenreTemplateError,
    NovelProfileError,
    NovelProfileRepository,
    apply_template,
    resolve_creator_context,
    list_templates,
)
from novelforge.story_engine.world_view import world_snapshot
from novelforge.story_engine.character_view import character_snapshot_payload
from novelforge.story_engine.plot_view import plot_snapshot
from novelforge.story_engine.progression_view import progression_snapshot
from novelforge.story_engine.memory_view import memory_snapshot
from novelforge.story_engine.director_view import apply_director_weights, director_snapshot
from novelforge.story_engine.linkage_view import linkage_snapshot
from novelforge.story_engine.driver import (
    advance_story,
    runtime_candidates,
    runtime_tick,
)
from novelforge.story_engine.storage import StoryStateRepository, StoryStateStorageError
from novelforge.story_engine.creator import DEFAULT_BRANCH
from novelforge.story_engine.creator import without_preview_flag
from novelforge.story_engine.creative import (
    CreativeBrief,
    CreativeBriefError,
    load_creative_brief,
    save_creative_brief,
    suggest_creative_brief,
    suggestion_from_profile,
)
from novelforge.story_engine.settings_gen import (
    SELECTABLE_GROUPS,
    SettingSeed,
    SettingsGenError,
    build_setting_seed,
    content_pack_draft,
    default_pack_id,
    load_pack_draft,
    load_setting_seed,
    save_setting_seed,
    saved_pack_id,
)
from novelforge.story_engine.settings_check import (
    check_seed,
    repair_and_save,
    run_settings_check,
)
from novelforge.story_engine.route_lab import (
    BranchLabError,
    compare_branches,
    fork_branch,
    freeze_branch,
    list_branches,
    merge_branches,
    merge_preview,
)
from novelforge.story_engine.outline_forge import (
    OutlineForgeError,
    StructureSpec,
    assess_forge_plan,
    build_forge_plan,
    export_forge_markdown,
    forge_outline,
    load_forge_chain,
)
from novelforge.story_engine.outline_revision import (
    RevisionError,
    diff_versions,
    export_outline as export_outline_bundle,
    impact_of_change,
    list_versions,
    merge_versions,
    restore_version,
    revise_item,
)

from novelforge.story_builder import (
    AIRecommendationSupplementer,
    DeterministicRecommendationEngine,
    SelectionSource,
    StoryCatalogError,
    StoryCatalogIndex,
    StoryBlueprintCompiler,
    StoryBlueprintError,
    StoryBlueprintRepository,
    StorySessionError,
    StorySessionManager,
    StorySessionRepository,
    StoryStep,
    OutlineLevel,
    StoryOutlineCompiler,
    StoryOutlineError,
    StoryOutlineRepository,
    load_story_catalog,
)
from novelforge.story_builder.ui_flow import (
    guided_flow_state,
    region_cards,
    relationship_graph,
    setting_impact,
    setting_overview,
)
from novelforge.story_builder.inspector import (
    inspector_overview,
    inspector_record,
    inspector_search,
    repair_diagnosis,
    repair_history,
)
from novelforge.story_builder.v3_projection import (
    command_center as v3_command_center,
    novel_cards as v3_novel_cards,
)
from novelforge.application.services import (
    journey_service,
    project_service,
)
from novelforge.story_builder.novel_admin import (
    NovelAdminError,
    archive_novel,
    rename_novel,
)
from novelforge.story_builder.writer_integration import (
    WriterContextBuilder,
    WriterDraftService,
    writer_export_bundle,
)


class APIRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateSessionRequest(APIRequest):
    project_id: str = "novel_project"
    session_id: str | None = None
    entry_step: Literal["reader_experience", "worldview", "protagonist", "major_events"] = "reader_experience"


class SetSelectionsRequest(APIRequest):
    step: StoryStep
    option_ids: list[str] = Field(default_factory=list)
    custom_texts: list[str] = Field(default_factory=list)
    expected_selection_version: int = Field(ge=0)
    option_source: SelectionSource = SelectionSource.AUTHOR


class BackRequest(APIRequest):
    target_step: StoryStep
    expected_selection_version: int = Field(ge=0)


class CreateNovelRequest(APIRequest):
    novel_id: str = Field(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96)
    title: str = Field(default="", max_length=120)
    genre: str = Field(default="", max_length=64)
    template_id: str = Field(default="", max_length=64)
    content_pack_id: str = Field(default="", max_length=64)


class RecommendationRequest(APIRequest):
    step: StoryStep | None = None
    limit: int = Field(default=5, ge=1, le=5)


class SaveSessionRequest(APIRequest):
    expected_selection_version: int = Field(ge=0)


class DirectorWeightsRequest(APIRequest):
    """导演权重：只允许改配置数值，不允许提交评分算法。"""

    weights: dict[str, float] = Field(default_factory=dict)


class RuntimeAdvanceRequest(APIRequest):
    """运行态推进：action_id 由引擎判定合法性，不接受客户端自证。"""

    action_id: str = Field(default="", max_length=128)
    actor: str = Field(default="", max_length=128)
    expected_revision: int | None = Field(default=None, ge=0)
    fire_events: list[str] = Field(default_factory=list)
    branch_id: str = Field(default="main", min_length=1, max_length=80)


class RuntimeTickRequest(APIRequest):
    actor: str = Field(default="", max_length=128)
    expected_revision: int | None = Field(default=None, ge=0)
    branch_id: str = Field(default="main", min_length=1, max_length=80)


class RuntimeForkRequest(APIRequest):
    """分支 fork：只从源分支深拷贝，不改源分支。"""

    source_branch: str = Field(default="main", min_length=1, max_length=80)
    target_branch: str = Field(min_length=1, max_length=80)


class RuntimeStartRequest(APIRequest):
    """W1-04：显式开始推演（自检通过后建立并落盘起点 StoryState）。"""

    branch_id: str = Field(default="main", min_length=1, max_length=80)
    expected_revision: int | None = Field(default=None, ge=0)


class CreativeIdeaRequest(APIRequest):
    """W1-01：一句创意 → 题材 / 基调 / 卖点候选。"""

    idea: str = Field(default="", max_length=1000)
    references: list[str] = Field(default_factory=list)
    reader_experience: str = Field(default="", max_length=300)
    selected_genre: str = Field(default="", max_length=64)
    regenerate: bool = False


class CreativeBriefRequest(APIRequest):
    original_idea: str = Field(max_length=1000)
    references: list[str] = Field(default_factory=list)
    reader_experience: str = Field(default="", max_length=300)
    selected_genre: str = Field(default="", max_length=64)
    selected_template_id: str = Field(default="", max_length=64)
    selected_content_pack_id: str = Field(default="", max_length=96)
    tone: str = Field(default="", max_length=64)
    selling_points: list[str] = Field(default_factory=list)


class SettingSeedRequest(APIRequest):
    """W1-02：生成设定候选（作者可要求换一批）。"""

    regenerate: bool = False
    selected: dict[str, list[str]] = Field(default_factory=dict)


class SettingSeedSaveRequest(APIRequest):
    """W1-02：保存作者确认 / 改写后的设定种子（不接受额外字段）。"""

    seed: dict[str, Any] = Field(default_factory=dict)
    selected: dict[str, list[str]] = Field(default_factory=dict)
    pack_id: str = Field(default="", max_length=96)


class SettingsCheckRequest(APIRequest):
    """W1-03：设定自检；可要求对可修补的缺项做数据层兜底。"""

    repair: bool = False
    seed: dict[str, Any] | None = None


class WriterDraftRequest(APIRequest):
    """M16B：writer 草稿输入（writer 声明的事实 claim 由既有校验处理）。"""

    novel_id: str = Field(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96)
    branch_id: str = Field(default=DEFAULT_BRANCH, max_length=80)
    chapter_id: str = Field(default="", max_length=128)
    event_id: str = Field(default="", max_length=128)
    narration: str = Field(default="", max_length=20000)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    new_facts: list[dict[str, Any]] = Field(default_factory=list)
    style: dict[str, str] = Field(default_factory=dict)


class BranchForkRequest(APIRequest):
    """W2：从某条分支复制出一条试演分支。"""

    source_branch: str = Field(default="main", min_length=1, max_length=80)
    label: str = Field(default="", max_length=60)


class BranchMergeRequest(APIRequest):
    """W2：把来源分支里被选中的成果合并进目标分支（只重放效果）。"""

    target_branch: str = Field(min_length=1, max_length=80)
    source_branches: list[str] = Field(min_length=1)
    item_keys: list[str] = Field(default_factory=list)


class BranchFreezeRequest(APIRequest):
    branch_id: str = Field(default="main", min_length=1, max_length=80)
    label: str = Field(default="", max_length=60)


class OutlineForgeRequest(APIRequest):
    """W3：把一条路线锻造成四级大纲。"""

    branch_id: str = Field(default="main", min_length=1, max_length=80)
    volumes: int = Field(default=3, ge=1, le=12)
    arcs_per_volume: int = Field(default=2, ge=1, le=6)
    chapters_per_arc: int = Field(default=5, ge=1, le=20)
    expected_revision: int | None = Field(default=None, ge=0)


class OutlineConfirmRequest(APIRequest):
    """W3：确认整条大纲链（沿用既有 confirm 规则）。"""

    branch_id: str = Field(default="main", min_length=1, max_length=80)


class OutlineReviseRequest(APIRequest):
    """W4：改写一个条目并查看联动影响。"""

    branch_id: str = Field(default="main", min_length=1, max_length=80)
    package_id: str = Field(min_length=3, max_length=96)
    item_id: str = Field(min_length=3, max_length=96)
    expected_version: int = Field(ge=1)
    changes: dict[str, Any] = Field(default_factory=dict)


class OutlineRestoreRequest(APIRequest):
    package_id: str = Field(min_length=3, max_length=96)
    version: int = Field(ge=1)


class OutlineMergeVersionsRequest(APIRequest):
    package_id: str = Field(min_length=3, max_length=96)
    base_version: int = Field(ge=1)
    source_version: int = Field(ge=1)
    item_ids: list[str] = Field(default_factory=list)


class ConfirmBlueprintRequest(APIRequest):
    version: int = Field(ge=1)


class CompileOutlineRequest(APIRequest):
    blueprint_version: int = Field(ge=1)
    regenerate: bool = False


class ConfirmOutlineRequest(APIRequest):
    version: int = Field(ge=1)


class AdventureChoiceRequest(APIRequest):
    revision: int = Field(ge=0)
    choice_id: str


class ForkAdventureRequest(APIRequest):
    parent_branch: str = "main"
    at_revision: int = Field(ge=0)
    expected_revision: int = Field(ge=0)
    request_id: UUID


class RouteOutlineRequest(APIRequest):
    branch_id: str = "main"
    expected_revision: int = Field(ge=1)


class OutlineChanges(APIRequest):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    summary: str | None = Field(default=None, min_length=1, max_length=4000)
    start_state: str | None = Field(default=None, max_length=2000)
    end_state: str | None = Field(default=None, max_length=2000)
    ending_hook: str | None = Field(default=None, max_length=1000)
    pov: str | None = Field(default=None, max_length=500)
    time: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=500)
    goals: list[str] | None = None
    conflicts: list[str] | None = None
    major_turns: list[str] | None = None
    participants: list[str] | None = None
    information_changes: list[str] | None = None
    costs: list[str] | None = None


class EditOutlineRequest(APIRequest):
    expected_version: int = Field(ge=1)
    changes: OutlineChanges


class DesignChoiceRequest(APIRequest):
    expected_selection_version: int = Field(ge=0)
    option_id: str | None = None
    custom_text: str = Field(default="", max_length=500)


class NovelRenameRequest(APIRequest):
    """NF-011：作品重命名（只改作者可见名字）。"""

    title: str = Field(min_length=1, max_length=120)


def create_story_builder_router(
    project_root: Path,
    *,
    catalog: StoryCatalogIndex | None = None,
    provider: Any | None = None,
) -> APIRouter:
    index = catalog or load_story_catalog(project_root)
    repository = StorySessionRepository(project_root)
    manager = StorySessionManager(repository, index)
    blueprint_repository = StoryBlueprintRepository(project_root)
    blueprint_compiler = StoryBlueprintCompiler(index, repository, blueprint_repository)
    outline_repository = StoryOutlineRepository(project_root)
    outline_compiler = StoryOutlineCompiler(index, blueprint_repository, outline_repository)
    rules = DeterministicRecommendationEngine(index)
    recommendations = AIRecommendationSupplementer(rules, provider)
    router = APIRouter(prefix="/api/story-builder", tags=["故事构筑"])
    adventure = AdventureEngine(project_root)
    profiles = NovelProfileRepository(project_root)

    def author_message(text: Any, state: Any = None, pack: Any = None) -> str:
        """把引擎错误文案翻成作者语言（NF-004 / NF-008）。

        错误信息是最容易泄漏内部标识的地方（`需要 protagonist 的 favors >= 1份`）。
        这里复用投影 / 导出同一张映射表，保证同一个 id 在所有位置说法一致。
        """

        from novelforge.author_language import label_table, translate
        from novelforge.story_engine.outline_forge import naming_table

        extra: dict[str, str] = {}
        try:
            if state is not None:
                extra = naming_table(state, pack)
        except Exception:  # noqa: BLE001 - 名称表不可用时仍然做关键词翻译
            extra = {}
        return translate(text, label_table(pack, extra=extra))

    @router.post("/blueprints/{blueprint_id}/adventures/{version}/outline")
    def compile_route_outline(blueprint_id: str, version: int, body: RouteOutlineRequest):
        return {"outline": outline_compiler.compile_route(blueprint_id, version, body.branch_id, body.expected_revision).model_dump(mode='json')}

    @router.get("/blueprints/{blueprint_id}/adventures/{version}/author-plan")
    def adventure_author_plan(blueprint_id: str, version: int):
        return adventure.author_plan(blueprint_id, version)

    @router.get("/blueprints/{blueprint_id}/adventures/{version}/branches")
    def list_adventure_branches(blueprint_id: str, version: int):
        return {"branches": adventure.branches(blueprint_id, version)}

    @router.post("/blueprints/{blueprint_id}/adventures/{version}/branches")
    def fork_adventure(blueprint_id: str, version: int, body: ForkAdventureRequest):
        return adventure.fork(blueprint_id, version, body.parent_branch, body.at_revision, body.expected_revision, str(body.request_id))

    @router.post("/blueprints/{blueprint_id}/adventures/{version}/branches/{branch_id}")
    def resume_branch(blueprint_id: str, version: int, branch_id: str):
        return adventure.start(blueprint_id, version, branch_id)

    @router.post("/blueprints/{blueprint_id}/adventures/{version}/branches/{branch_id}/choices")
    def choose_branch(blueprint_id: str, version: int, branch_id: str, body: AdventureChoiceRequest):
        return adventure.choose(blueprint_id, version, body.revision, body.choice_id, branch_id)

    @router.post("/blueprints/{blueprint_id}/adventures/{version}")
    def start_adventure(blueprint_id: str, version: int):
        return adventure.start(blueprint_id, version)

    @router.post("/blueprints/{blueprint_id}/adventures/{version}/choices")
    def choose_adventure(blueprint_id: str, version: int, body: AdventureChoiceRequest):
        return adventure.choose(blueprint_id, version, body.revision, body.choice_id)

    def session_payload(session_id: str) -> dict[str, Any]:
        session = repository.load(session_id)
        current = index.require_step(session.current_step)
        novel = profiles.ensure(session.project_id)
        return {
            "session": session.model_dump(mode="json"),
            "novel": novel.model_dump(mode="json"),
            "design_tree": design_view(index, session),
            "current_step": current.model_dump(mode="json"),
            "selected": [
                {
                    **selection.model_dump(mode="json"),
                    "display_name": (
                        index.require_option(selection.option_id).name
                        if selection.option_id
                        else selection.custom_text
                    ),
                }
                for selection in session.selections
            ],
        }

    @router.get("/novels")
    def list_novels() -> dict[str, Any]:
        # V4-01：应用服务边界 —— 路由不再自己拼投影（见 ADR-001）。
        return {"novels": project_service(project_root).list_novels()}

    @router.post("/novels", status_code=201)
    def create_novel(body: CreateNovelRequest) -> dict[str, Any]:
        novel = project_service(project_root).create_novel(
            body.novel_id, title=body.title, genre=body.genre,
            content_pack_id=body.content_pack_id, template_id=body.template_id)
        return {"novel": novel}

    @router.get("/content-packs")
    def list_content_packs() -> dict[str, Any]:
        from novelforge.story_engine.content import list_packs_from_project

        return {"packs": [{"pack_id": item.pack_id, "title": item.title, "genre": item.genre}
                          for item in list_packs_from_project(project_root)]}

    @router.get("/novels/{novel_id}")
    def get_novel(novel_id: str) -> dict[str, Any]:
        return {"novel": project_service(project_root).get_novel(novel_id)}

    @router.patch("/novels/{novel_id}")
    def rename_novel_route(novel_id: str, body: NovelRenameRequest) -> dict[str, Any]:
        """NF-011：改作者可见的作品名（只改名字，不动任何事实）。"""

        try:
            return project_service(project_root).rename_novel(novel_id, body.title)
        except NovelAdminError as exc:
            status = 404 if exc.code == "PROFILE_NOT_FOUND" else 422
            raise HTTPException(status_code=status, detail=exc.as_dict()) from exc

    @router.delete("/novels/{novel_id}")
    def delete_novel_route(novel_id: str, confirm: bool = Query(default=False),
                           reason: str = Query(default="", max_length=200)
                           ) -> dict[str, Any]:
        """NF-011：删除作品＝整体归档（二次确认 + 可恢复 + 不留孤儿）。"""

        if not confirm:
            raise HTTPException(status_code=409, detail={
                "code": "NOVEL_DELETE_UNCONFIRMED",
                "message": "删除作品需要二次确认：请带上 confirm=true。",
                "novel_id": novel_id})
        try:
            return project_service(project_root).archive_novel(novel_id, reason=reason)
        except NovelAdminError as exc:
            status = 404 if exc.code == "PROFILE_NOT_FOUND" else 422
            raise HTTPException(status_code=status, detail=exc.as_dict()) from exc

    @router.get("/creator/world")
    def creator_world(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96)) -> dict[str, Any]:
        """V2-I-01 世界面板：时间 / 地点 / 势力 / 世界事件 / 自主行动（只读）。"""

        try:
            context = resolve_creator_context(project_root, novel_id)
        except CreatorContextError as exc:
            raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        return world_snapshot(context)

    @router.get("/creator/characters")
    def creator_characters(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
        character_id: str = Query(default="", max_length=128),
        reactions: bool = Query(default=True),
    ) -> dict[str, Any]:
        """V2-I-02 角色面板：目标 / 记忆 / 关系 / 人物弧 / 自主行动 / 反应理由（只读）。"""

        try:
            context = resolve_creator_context(project_root, novel_id)
        except CreatorContextError as exc:
            raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        return character_snapshot_payload(context, character_id, include_reactions=reactions)

    @router.get("/creator/plot")
    def creator_plot(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
        actor: str = Query(default="", max_length=128),
    ) -> dict[str, Any]:
        """V2-I-03 剧情面板：候选行动、当前事件、支线、事件连锁、世界影响（只读）。"""

        try:
            context = resolve_creator_context(project_root, novel_id)
        except CreatorContextError as exc:
            raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        return plot_snapshot(context, actor=actor)

    @router.get("/creator/progression")
    def creator_progression(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
        actor: str = Query(default="", max_length=128),
        category: str = Query(default="", max_length=32),
    ) -> dict[str, Any]:
        """V2-I-04 成长面板：七类 Progression 的 owned / available / locked（只读）。"""

        try:
            context = resolve_creator_context(project_root, novel_id)
        except CreatorContextError as exc:
            raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        payload = progression_snapshot(context, actor=actor)
        if category:
            payload["categories"] = [item for item in payload["categories"]
                                     if item["category"] == category]
            payload["trees"] = [
                {**tree, "nodes": [node for node in tree["nodes"] if node["category"] == category]}
                for tree in payload["trees"]
            ]
        return payload

    @router.get("/creator/memory")
    def creator_memory(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96)) -> dict[str, Any]:
        """V2-I-05 记忆面板：三视角知识、承诺 / 债务 / 人情、仇恨来源、未解决冲突与伏笔（只读）。"""

        try:
            context = resolve_creator_context(project_root, novel_id)
        except CreatorContextError as exc:
            raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        return memory_snapshot(context)

    @router.get("/creator/director")
    def creator_director(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
        actor: str = Query(default="", max_length=128),
    ) -> dict[str, Any]:
        """V2-I-06 导演面板：候选事件排序、chosen、逐维得分与权重（只读）。"""

        try:
            context = resolve_creator_context(project_root, novel_id)
        except CreatorContextError as exc:
            raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        return director_snapshot(context, actor=actor)

    @router.put("/creator/director/weights")
    def update_director_weights(novel_id: str, body: DirectorWeightsRequest) -> dict[str, Any]:
        """权重调整只改配置；评分仍然由 director.py 计算。"""

        try:
            context = resolve_creator_context(project_root, novel_id)
        except CreatorContextError as exc:
            raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        if not body.weights:
            raise HTTPException(status_code=422, detail={"message": "请至少提交一个权重字段"})
        try:
            profile = apply_director_weights(context, body.weights)
        except Exception as exc:  # noqa: BLE001 - 权重非法时返回 422
            raise HTTPException(status_code=422, detail={"message": f"权重不合法：{exc}"}) from exc
        refreshed = resolve_creator_context(project_root, novel_id)
        return {"novel": profile.model_dump(mode="json"), "director": director_snapshot(refreshed)}

    @router.get("/creator/linkage")
    def creator_linkage(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
        preview: bool = Query(default=False),
        changed_stage: str = Query(default="", max_length=64),
        note: str = Query(default="", max_length=300),
    ) -> dict[str, Any]:
        """V2-I-07 大纲联动面板：StoryState → 路线 → 全书 / 卷 / 篇章 / 章节（只读，可预览重规划）。"""

        try:
            context = resolve_creator_context(project_root, novel_id)
        except CreatorContextError as exc:
            raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        try:
            return linkage_snapshot(context, changed_stage=changed_stage, note=note, preview=preview)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc

    def _runtime_context(novel_id: str, branch_id: str = DEFAULT_BRANCH, *,
                         require_started: bool = False):
        """运行态上下文：小说 + 内容包 + 蓝图 + 指定分支的 StoryState（只读加载）。

        branch_id 必须显式传入：不同分支的状态文件完全独立
        （`vXXXXXX.json` 与 `vXXXXXX_<branch>.json`），互不覆盖。
        没有确认蓝图的小说（W1 引导流程）用小说级运行槽；未开始时只给预览状态。
        `require_started=True` 时，没有蓝图也没有显式开始过的小说会被拒绝写入。
        """

        context = resolve_creator_context(project_root, novel_id)
        if context.pack is None:
            raise HTTPException(status_code=422, detail={
                "code": "CONTENT_PACK_REQUIRED",
                "message": "当前小说没有可用的内容包，无法推进运行态。"})
        states = StoryStateRepository(project_root)
        state = context.state
        if context.persisted and context.runtime_id and states.exists(
                context.runtime_id, context.runtime_version, branch_id):
            try:
                state = states.load(context.runtime_id, context.runtime_version, branch_id)
            except StoryStateStorageError as exc:
                raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        else:
            state = without_preview_flag(state)
        if require_started and not context.persisted and not context.blueprint_id:
            raise HTTPException(status_code=409, detail={
                "code": "STORY_NOT_STARTED",
                "message": "这本小说还没有开始推演；请先执行开始推演（runtime/start）。"})
        return context, states, state, branch_id

    def _persist_runtime(context, states, state, branch_id: str = DEFAULT_BRANCH) -> None:
        """写入该小说的事实槽（蓝图槽或小说级运行槽）的指定分支，不触碰其它分支。"""

        states.save(without_preview_flag(state), context.runtime_id,
                    context.runtime_version, branch_id)

    def _branch_error(exc: BranchLabError) -> HTTPException:
        status = 404 if exc.code in ("BRANCH_NOT_FOUND", "CONTENT_PACK_REQUIRED") else 409 \
            if exc.code in ("BRANCH_EXISTS", "MERGE_SAME_BRANCH") else 422
        return HTTPException(status_code=status, detail=exc.as_dict())

    def _forge_error(exc: OutlineForgeError) -> HTTPException:
        status = 404 if exc.code in ("ROUTE_NOT_STARTED", "OUTLINE_NOT_FOUND",
                                     "CONTENT_PACK_REQUIRED") else 409 \
            if exc.code == "OUTLINE_ROUTE_STALE" else 422
        return HTTPException(status_code=status, detail=exc.as_dict())

    @router.get("/outline/plan")
    def get_outline_plan(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
        branch_id: str = Query(default=DEFAULT_BRANCH, max_length=80),
        volumes: int = Query(default=3, ge=1, le=12),
        arcs_per_volume: int = Query(default=2, ge=1, le=6),
        chapters_per_arc: int = Query(default=5, ge=1, le=20),
    ) -> dict[str, Any]:
        """W3：只读预览——这条路线会生成什么规模的四级大纲、质量如何。"""

        structure = StructureSpec(volumes=volumes, arcs_per_volume=arcs_per_volume,
                                  chapters_per_arc=chapters_per_arc)
        try:
            plan = build_forge_plan(project_root, novel_id, branch_id=branch_id,
                                    structure=structure)
        except OutlineForgeError as exc:
            raise _forge_error(exc) from exc
        return {"novel_id": novel_id, "branch_id": branch_id, "plan": plan.as_dict(),
                "quality": assess_forge_plan(plan).as_dict()}

    @router.post("/outline/forge")
    def post_outline_forge(novel_id: str, body: OutlineForgeRequest) -> dict[str, Any]:
        """W3：剧情 → 全书主线 / 卷纲 / 篇章纲 / 详细章纲（复用既有大纲仓库）。"""

        structure = StructureSpec(volumes=body.volumes, arcs_per_volume=body.arcs_per_volume,
                                  chapters_per_arc=body.chapters_per_arc)
        try:
            return forge_outline(project_root, novel_id, branch_id=body.branch_id,
                                 structure=structure, provider=provider,
                                 expected_revision=body.expected_revision)
        except OutlineForgeError as exc:
            raise _forge_error(exc) from exc

    @router.get("/outline/chain")
    def get_outline_chain(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
        branch_id: str = Query(default=DEFAULT_BRANCH, max_length=80),
    ) -> dict[str, Any]:
        """W3：读取已锻造的四级大纲链（含来源是否仍一致）。"""

        try:
            chain = load_forge_chain(project_root, novel_id, branch_id=branch_id)
        except OutlineForgeError as exc:
            raise _forge_error(exc) from exc
        return {key: (value.model_dump(mode="json") if hasattr(value, "model_dump")
                      else [item.model_dump(mode="json") for item in value] if isinstance(value, list)
                      else value)
                for key, value in chain.items()}

    @router.get("/outline/export")
    def get_outline_export(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
        branch_id: str = Query(default=DEFAULT_BRANCH, max_length=80),
        format: str = Query(default="markdown", max_length=16),
    ) -> dict[str, Any]:
        """W3/W4：导出大纲（markdown / json / docx）。"""

        try:
            return export_outline_bundle(project_root, novel_id, branch_id=branch_id, fmt=format)
        except RevisionError as exc:
            raise _revision_error(exc) from exc
        except OutlineForgeError as exc:
            raise _forge_error(exc) from exc

    def _revision_error(exc: RevisionError) -> HTTPException:
        status = 404 if exc.code in ("OUTLINE_NOT_FOUND", "OUTLINE_ITEM_NOT_FOUND") else 409 \
            if exc.code in ("OUTLINE_SOURCE_STALE", "OUTLINE_VERSION_STALE") else 422
        return HTTPException(status_code=status, detail=exc.as_dict())

    @router.get("/outline/versions")
    def get_outline_versions(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
        package_id: str = Query(min_length=3, max_length=96),
    ) -> dict[str, Any]:
        """W4-02：列出某个大纲包的所有版本（含确认状态）。"""

        try:
            return list_versions(project_root, novel_id, package_id)
        except RevisionError as exc:
            raise _revision_error(exc) from exc

    @router.get("/outline/version-diff")
    def get_outline_version_diff(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
        package_id: str = Query(min_length=3, max_length=96),
        from_version: int = Query(ge=1),
        to_version: int = Query(ge=1),
    ) -> dict[str, Any]:
        """W4-02：比较两个版本（逐条列出改了哪些字段）。"""

        try:
            return diff_versions(project_root, novel_id, package_id,
                                 from_version=from_version, to_version=to_version).as_dict()
        except RevisionError as exc:
            raise _revision_error(exc) from exc

    @router.get("/outline/impact")
    def get_outline_impact(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
        branch_id: str = Query(default=DEFAULT_BRANCH, max_length=80),
        package_id: str = Query(min_length=3, max_length=96),
        item_id: str = Query(min_length=3, max_length=96),
    ) -> dict[str, Any]:
        """W4-01：只读预览——改这个条目会影响哪些下游包。"""

        try:
            return impact_of_change(project_root, novel_id, branch_id=branch_id,
                                    package_id=package_id, item_id=item_id)
        except RevisionError as exc:
            raise _revision_error(exc) from exc

    @router.post("/outline/revise")
    def post_outline_revise(novel_id: str, body: OutlineReviseRequest) -> dict[str, Any]:
        """W4-01：改写条目（只允许写作设计字段）并返回联动影响。"""

        try:
            return revise_item(project_root, novel_id, branch_id=body.branch_id,
                               package_id=body.package_id, item_id=body.item_id,
                               changes=body.changes, expected_version=body.expected_version)
        except RevisionError as exc:
            raise _revision_error(exc) from exc
        except Exception as exc:  # noqa: BLE001 - 版本冲突 / 非法字段按 422 返回
            raise HTTPException(status_code=422, detail={
                "code": "OUTLINE_REVISE_FAILED", "message": str(exc),
                "package_id": body.package_id}) from exc

    @router.post("/outline/restore")
    def post_outline_restore(novel_id: str, body: OutlineRestoreRequest) -> dict[str, Any]:
        """W4-02：回退到旧版本（生成新版本，历史版本继续保留）。"""

        try:
            return restore_version(project_root, novel_id, package_id=body.package_id,
                                   version=body.version)
        except RevisionError as exc:
            raise _revision_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail={
                "code": "OUTLINE_RESTORE_FAILED", "message": str(exc),
                "package_id": body.package_id}) from exc

    @router.post("/outline/merge-versions")
    def post_outline_merge_versions(novel_id: str,
                                    body: OutlineMergeVersionsRequest) -> dict[str, Any]:
        """W4-02：把来源版本里选中的条目合并到基准版本的新副本上。"""

        try:
            return merge_versions(project_root, novel_id, package_id=body.package_id,
                                  base_version=body.base_version,
                                  source_version=body.source_version,
                                  item_ids=body.item_ids or None)
        except RevisionError as exc:
            raise _revision_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail={
                "code": "OUTLINE_MERGE_FAILED", "message": str(exc),
                "package_id": body.package_id}) from exc

    @router.post("/outline/confirm")
    def post_outline_confirm(
        novel_id: str,
        body: OutlineConfirmRequest,
    ) -> dict[str, Any]:
        """W3：按 全书 → 卷 → 篇章 → 章节 的顺序确认整条大纲链（确认后才能逐条改写）。"""

        try:
            chain = load_forge_chain(project_root, novel_id, branch_id=body.branch_id)
        except OutlineForgeError as exc:
            raise _forge_error(exc) from exc
        book = chain.get("book")
        if book is None:
            raise HTTPException(status_code=404, detail={
                "code": "OUTLINE_NOT_FOUND", "message": "还没有锻造过大纲", "novel_id": novel_id})
        ordered = [book, *chain["volumes"], *chain["arcs"], *chain["chapters"]]
        confirmed: list[dict[str, Any]] = []
        for package in ordered:
            latest = outline_repository.latest(package.level, package.package_id)
            if latest is None:
                continue
            if latest.status.name == "CONFIRMED":
                confirmed.append({"package_id": latest.package_id, "level": latest.level.value,
                                  "version": latest.version, "already": True})
                continue
            try:
                done = outline_compiler.confirm(latest.package_id, latest.version)
            except Exception as exc:  # noqa: BLE001 - 逐层返回可读原因
                raise HTTPException(status_code=409, detail={
                    "code": getattr(exc, "code", "OUTLINE_CONFIRM_FAILED"),
                    "message": str(exc), "package_id": latest.package_id}) from exc
            confirmed.append({"package_id": done.package_id, "level": done.level.value,
                              "version": done.version, "already": False})
        return {"novel_id": novel_id, "branch_id": body.branch_id,
                "confirmed": confirmed, "count": len(confirmed)}

    @router.get("/runtime/branches")
    def runtime_branches(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3,
                                               max_length=96)) -> dict[str, Any]:
        """W2-01：列出试演分支与正式路线标记（只读）。"""

        try:
            return list_branches(project_root, novel_id)
        except BranchLabError as exc:
            raise _branch_error(exc) from exc

    @router.post("/runtime/branches/fork")
    def runtime_branch_fork(novel_id: str, body: BranchForkRequest) -> dict[str, Any]:
        """W2-01：从当前事实复制出一条独立试演分支。"""

        try:
            return fork_branch(project_root, novel_id, source_branch=body.source_branch,
                               label=body.label)
        except BranchLabError as exc:
            raise _branch_error(exc) from exc

    @router.get("/runtime/branches/compare")
    def runtime_branch_compare(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
        base_branch: str = Query(default=DEFAULT_BRANCH, max_length=80),
        target_branch: str = Query(default="", max_length=80),
    ) -> dict[str, Any]:
        """W2-01：结构化对比两条分支（关系 / 知识 / 支线 / 伏笔 / 资源 / 身份 / 能力）。"""

        try:
            return compare_branches(project_root, novel_id, base_branch=base_branch,
                                    target_branch=target_branch).as_dict()
        except BranchLabError as exc:
            raise _branch_error(exc) from exc

    @router.post("/runtime/branches/merge/preview")
    def runtime_branch_merge_preview(novel_id: str, body: BranchMergeRequest) -> dict[str, Any]:
        """W2-02：只读预览合并结果（哪些能搬、哪些冲突）。"""

        try:
            return merge_preview(project_root, novel_id, target_branch=body.target_branch,
                                 source_branches=body.source_branches)
        except BranchLabError as exc:
            raise _branch_error(exc) from exc

    @router.post("/runtime/branches/merge")
    def runtime_branch_merge(novel_id: str, body: BranchMergeRequest) -> dict[str, Any]:
        """W2-02：把选中的成果合并进目标分支；历史只追加，不改写。"""

        try:
            return merge_branches(project_root, novel_id, target_branch=body.target_branch,
                                  source_branches=body.source_branches,
                                  item_keys=body.item_keys or None).model_dump(mode="json")
        except BranchLabError as exc:
            raise _branch_error(exc) from exc

    @router.post("/runtime/branches/freeze")
    def runtime_branch_freeze(novel_id: str, body: BranchFreezeRequest) -> dict[str, Any]:
        """W2-03：把某条分支标记为正式路线并留下快照。"""

        try:
            return freeze_branch(project_root, novel_id, branch_id=body.branch_id,
                                 label=body.label)
        except BranchLabError as exc:
            raise _branch_error(exc) from exc

    @router.get("/runtime/state")
    def runtime_state(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
                      actor: str = Query(default="", max_length=128),
                      branch_id: str = Query(default=DEFAULT_BRANCH, max_length=80)) -> dict[str, Any]:
        """V2 运行态：当前事实摘要 + 由状态生成的合法候选行动（只读）。

        `started=false` 表示这本小说还没开始推演，返回的是与引擎同源的只读预览状态。
        """

        try:
            context, _, state, resolved_branch = _runtime_context(novel_id, branch_id)
        except CreatorContextError as exc:
            raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        payload = runtime_candidates(state, context.pack, actor=actor)
        payload["meta"] = context.meta()
        payload["started"] = context.persisted
        payload["runtime_id"] = context.runtime_id
        payload["branch_id"] = resolved_branch
        return payload

    @router.post("/runtime/start")
    def runtime_start(novel_id: str, body: RuntimeStartRequest) -> dict[str, Any]:
        """W1-04：自检通过后显式开始推演，把起点事实落盘（幂等）。"""

        try:
            context = resolve_creator_context(project_root, novel_id)
        except CreatorContextError as exc:
            raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        if context.pack is None:
            raise HTTPException(status_code=422, detail={
                "code": "CONTENT_PACK_REQUIRED",
                "message": "当前小说没有可用的内容包，无法开始推演。"})
        try:
            report = run_settings_check(project_root, novel_id)
        except SettingsGenError as exc:
            raise HTTPException(status_code=_settings_error_status(exc), detail=exc.as_dict()) from exc
        if not report.ok:
            raise HTTPException(status_code=422, detail={
                "code": "SETTINGS_NOT_RUNNABLE",
                "message": "设定自检未通过，先修补缺项再开始推演。",
                "findings": [item.as_dict() for item in report.findings],
                "novel_id": novel_id})
        states = StoryStateRepository(project_root)
        started = False
        if states.exists(context.runtime_id, context.runtime_version, body.branch_id):
            state = states.load(context.runtime_id, context.runtime_version, body.branch_id)
        else:
            state = without_preview_flag(context.state)
            states.save(state, context.runtime_id, context.runtime_version, body.branch_id)
            started = True
        payload = runtime_candidates(state, context.pack, actor="")
        payload["meta"] = context.meta()
        payload["started"] = True
        payload["created"] = started
        payload["runtime_id"] = context.runtime_id
        payload["branch_id"] = body.branch_id
        payload["check"] = {"ok": report.ok, "findings": [item.as_dict()
                                                         for item in report.findings]}
        return payload

    @router.post("/runtime/advance")
    def runtime_advance(novel_id: str, body: RuntimeAdvanceRequest) -> dict[str, Any]:
        """推进一轮：候选 → 行动 → 效果 → 延迟 → 世界 / 事件 → 导演 → 表现 → 持久化 → 下一轮候选。"""

        try:
            context, states, state, branch_id = _runtime_context(novel_id, body.branch_id,
                                                                 require_started=True)
        except CreatorContextError as exc:
            raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        actor = body.actor or next(iter(state.characters), "protagonist")
        result = advance_story(state, context.pack, action_id=body.action_id, actor=actor,
                               expected_revision=body.expected_revision,
                               fire_events=body.fire_events)
        if not result.ok:
            status = 409 if result.blocked == "stale_revision" else 422
            raise HTTPException(status_code=status, detail={
                "code": result.blocked,
                "message": author_message(result.message, state, context.pack),
                "revision": result.revision,
                "blocked_actions": [
                    {**item, "reason": author_message(item.get("reason"), state,
                                                      context.pack)}
                    for item in result.next_candidates if not item.get("available")][:5]})
        _persist_runtime(context, states, result.state, branch_id)
        payload = result.as_dict()
        payload["meta"] = context.meta()
        payload["branch_id"] = branch_id
        return payload

    @router.post("/runtime/tick")
    def runtime_world_tick(novel_id: str, body: RuntimeTickRequest) -> dict[str, Any]:
        """主角不行动时的明确推进：世界 / NPC / 事件 / 延迟结算，然后重新计算候选。"""

        try:
            context, states, state, branch_id = _runtime_context(novel_id, body.branch_id,
                                                                 require_started=True)
        except CreatorContextError as exc:
            raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        actor = body.actor or next(iter(state.characters), "protagonist")
        result = runtime_tick(state, context.pack, actor=actor,
                              expected_revision=body.expected_revision)
        if not result.ok:
            raise HTTPException(status_code=409, detail={
                "code": result.blocked,
                "message": author_message(result.message, state, context.pack),
                "revision": result.revision})
        _persist_runtime(context, states, result.state, branch_id)
        payload = result.as_dict()
        payload["meta"] = context.meta()
        payload["branch_id"] = branch_id
        return payload

    @router.post("/runtime/fork")
    def runtime_fork(novel_id: str, body: RuntimeForkRequest) -> dict[str, Any]:
        """从某个分支的当前事实深拷贝出一个新分支；源分支与主线都不被修改。"""

        try:
            context, states, state, source_branch = _runtime_context(novel_id, body.source_branch,
                                                                     require_started=True)
        except CreatorContextError as exc:
            raise HTTPException(status_code=404, detail=exc.as_dict()) from exc
        source_path = states.path_for(context.runtime_id, context.runtime_version, source_branch)
        if not source_path.is_file():
            states.save(without_preview_flag(state), context.runtime_id, context.runtime_version,
                        source_branch)
        try:
            forked = states.fork(context.runtime_id, context.runtime_version,
                                 source_branch=source_branch, target_branch=body.target_branch)
        except StoryStateStorageError as exc:
            raise HTTPException(status_code=409, detail=exc.as_dict()) from exc
        return {"branch_id": body.target_branch, "source_branch": source_branch,
                "revision": len([item for item in forked.effect_log
                                 if item.op in ("choice", "runtime_action")]),
                "tick": forked.timeline.tick, "meta": context.meta()}

    @router.get("/templates")
    def get_templates() -> dict[str, Any]:
        return {"templates": [{"template_id": item.template_id, "name": item.name, "genre": item.genre,
                               "concepts": item.concepts, "rules": item.rules, "notes": item.notes}
                              for item in list_templates()]}

    @router.get("/creative/brief")
    def get_creative_brief(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3,
                                                 max_length=96)) -> dict[str, Any]:
        """W1-01：读取已保存的创意简报与候选（刷新恢复用）；没有保存时 suggestion 为 null。"""

        brief = load_creative_brief(project_root, novel_id)
        if brief is None:
            return {"novel_id": novel_id, "brief": None, "suggestion": None}
        suggestion = suggestion_from_profile(project_root, novel_id, provider=provider)
        return {"novel_id": novel_id, "brief": brief.as_dict(),
                "suggestion": suggestion.as_dict() if suggestion else None}

    @router.post("/creative/suggest")
    def suggest_creative(novel_id: str, body: CreativeIdeaRequest) -> dict[str, Any]:
        """W1-01：一句创意 → 题材候选 / 基调候选 / 卖点候选（候选全部指向真实目录）。"""

        try:
            suggestion = suggest_creative_brief(
                project_root, novel_id, idea=body.idea, references=body.references,
                reader_experience=body.reader_experience, selected_genre=body.selected_genre,
                regenerate=body.regenerate, provider=provider)
        except CreativeBriefError as exc:
            raise HTTPException(status_code=422, detail=exc.as_dict()) from exc
        return suggestion.as_dict()

    @router.put("/creative/brief")
    def put_creative_brief(novel_id: str, body: CreativeBriefRequest) -> dict[str, Any]:
        """W1-01：保存作者确认的创意简报（写入 NovelProfile，不写 StoryState）。"""

        try:
            profile, brief = save_creative_brief(project_root, novel_id,
                                                 CreativeBrief.model_validate(body.model_dump()))
        except CreativeBriefError as exc:
            status = 404 if exc.code in ("TEMPLATE_NOT_FOUND", "CONTENT_PACK_NOT_FOUND") else 422
            raise HTTPException(status_code=status, detail=exc.as_dict()) from exc
        return {"novel": profile.model_dump(mode="json"), "brief": brief.as_dict()}

    def _settings_error_status(exc: SettingsGenError) -> int:
        return 404 if exc.code in ("CREATIVE_BRIEF_REQUIRED", "CONTENT_PACK_NOT_FOUND",
                                   "SETTINGS_PACK_REQUIRED") else 422

    @router.get("/settings/seed")
    def get_settings_seed(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3,
                                                max_length=96)) -> dict[str, Any]:
        """W1-02：读取已保存的设定候选与内容包草稿（刷新恢复用）。"""

        seed = load_setting_seed(project_root, novel_id)
        pack_id = saved_pack_id(project_root, novel_id)
        pack = load_pack_draft(project_root, pack_id) if pack_id else None
        return {"novel_id": novel_id, "seed": seed.as_dict() if seed else None,
                "pack_id": pack_id,
                "pack": pack.model_dump(mode="json") if pack else None,
                "groups": list(SELECTABLE_GROUPS), "saved": seed is not None}

    @router.post("/settings/seed")
    def suggest_settings_seed(novel_id: str, body: SettingSeedRequest) -> dict[str, Any]:
        """W1-02：creative_brief → 8 组设定候选 + 可直接运行的内容包骨架预览。"""

        try:
            seed = build_setting_seed(project_root, novel_id, regenerate=body.regenerate,
                                      provider=provider, selected=body.selected or None)
            brief = load_creative_brief(project_root, novel_id)
            pack_id = default_pack_id(novel_id)
            pack_payload = (content_pack_draft(seed, pack_id=pack_id, brief=brief)
                            if brief is not None else {})
        except SettingsGenError as exc:
            raise HTTPException(status_code=_settings_error_status(exc), detail=exc.as_dict()) from exc
        return {"novel_id": novel_id, "seed": seed.as_dict(), "pack_id": pack_id,
                "pack_preview": pack_payload, "groups": list(SELECTABLE_GROUPS)}

    @router.put("/settings/seed")
    def put_settings_seed(novel_id: str, body: SettingSeedSaveRequest) -> dict[str, Any]:
        """W1-02：保存设定种子 + 生成内容包骨架（设计态；不写 StoryState）。"""

        try:
            seed = SettingSeed.model_validate(dict(body.seed))
            result = save_setting_seed(project_root, novel_id, seed=seed,
                                       selected=body.selected or None, pack_id=body.pack_id)
        except SettingsGenError as exc:
            raise HTTPException(status_code=_settings_error_status(exc), detail=exc.as_dict()) from exc
        except Exception as exc:  # noqa: BLE001 - schema 校验失败按 422 返回
            raise HTTPException(status_code=422, detail={
                "code": "SETTING_SEED_INVALID", "message": str(exc), "novel_id": novel_id}) from exc
        return {"novel_id": novel_id, "seed": seed.as_dict(), "pack_id": result["pack_id"],
                "pack": result["pack"].model_dump(mode="json"),
                "novel": result["profile"].model_dump(mode="json"),
                "notes": result["notes"]}

    @router.get("/settings/check")
    def get_settings_check(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3,
                                                 max_length=96)) -> dict[str, Any]:
        """W1-03：对已保存的设定做可运行性自检（只读，不写盘）。"""

        try:
            report = run_settings_check(project_root, novel_id)
        except SettingsGenError as exc:
            raise HTTPException(status_code=_settings_error_status(exc), detail=exc.as_dict()) from exc
        return report.as_dict()

    @router.post("/settings/check")
    def post_settings_check(novel_id: str, body: SettingsCheckRequest) -> dict[str, Any]:
        """W1-03：自检；`repair=true` 时先做数据层兜底再自检。"""

        try:
            if body.seed is not None:
                report = check_seed(project_root, novel_id, SettingSeed.model_validate(body.seed))
                return {**report.as_dict(), "repaired": False, "applied_fixes": []}
            fixes: list[str] = []
            if body.repair:
                fixes = repair_and_save(project_root, novel_id)["fixes"]
            report = run_settings_check(project_root, novel_id)
        except SettingsGenError as exc:
            raise HTTPException(status_code=_settings_error_status(exc), detail=exc.as_dict()) from exc
        except Exception as exc:  # noqa: BLE001 - schema 校验失败按 422 返回
            raise HTTPException(status_code=422, detail={
                "code": "SETTINGS_CHECK_INVALID", "message": str(exc),
                "novel_id": novel_id}) from exc
        return {**report.as_dict(), "repaired": bool(fixes), "applied_fixes": fixes}

    @router.get("/guided-flow")
    def get_guided_flow(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3,
                                              max_length=96)) -> dict[str, Any]:
        """W6-01 / W6-03：引导流状态（当前阶段 + 下一步）；只读，不写任何事实。"""

        return guided_flow_state(project_root, novel_id)

    # --------------------------------------------------------- Product V3 UI
    @router.get("/v3/novels")
    def v3_novels() -> dict[str, Any]:
        """Product V3 Landing：真实作品列表（游戏式存档选择），只读投影。"""

        return v3_novel_cards(project_root)

    @router.get("/v3/novels/{novel_id}/command-center")
    def v3_command_center_route(novel_id: str) -> dict[str, Any]:
        """Product V3 Novel Command Center：旅程 / 目标 / 下一步 / 风险，只读投影。"""

        return v3_command_center(project_root, novel_id)

    @router.get("/v3/novels/{novel_id}/journey")
    def v3_journey_route(novel_id: str) -> dict[str, Any]:
        """V4-01：canonical JourneyProjection（唯一阶段 / 进度 / 下一步入口）。

        UI / REST / 未来的 MCP resource 都消费这一个投影（ADR-004）。
        """

        return journey_service(project_root, novel_id).projection()

    @router.get("/settings/impact")
    def get_settings_impact(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3,
                                                  max_length=96),
                            group: str = Query(default="", max_length=32)) -> dict[str, Any]:
        """W6-04：候选 / 已选设定的影响范围投影（NovelProfile 字段 / 内容包段 / 解锁行动）。"""

        if group and group not in SELECTABLE_GROUPS:
            raise HTTPException(status_code=422, detail={
                "code": "SETTINGS_GROUP_UNKNOWN", "message": f"未知设定组：{group}",
                "novel_id": novel_id, "allowed": list(SELECTABLE_GROUPS)})
        return setting_impact(project_root, novel_id, group=group)

    @router.get("/settings/overview")
    def get_settings_overview(novel_id: str = Query(default=DEFAULT_NOVEL_ID,
                                                    min_length=3, max_length=96)
                              ) -> dict[str, Any]:
        """W6-07：设定总览卡（世界 / 主角 / 核心伙伴 / 势力 / 关系）；只读 planned 层。"""

        return setting_overview(project_root, novel_id)

    @router.get("/settings/regions")
    def get_settings_regions(novel_id: str = Query(default=DEFAULT_NOVEL_ID,
                                                   min_length=3, max_length=96)
                             ) -> dict[str, Any]:
        """W6-08：区域与地图卡片（危险度 / 已知资源 / 已知信息 / 进入条件）。"""

        return region_cards(project_root, novel_id)

    @router.get("/settings/relationships")
    def get_settings_relationships(novel_id: str = Query(default=DEFAULT_NOVEL_ID,
                                                         min_length=3, max_length=96),
                                   character_id: str = Query(default="", max_length=128)
                                   ) -> dict[str, Any]:
        """W6-09：关系网（人物 / 势力 / 伙伴）+ 数值来源与变更记录。"""

        return relationship_graph(project_root, novel_id, character_id=character_id)

    @router.get("/inspector/overview")
    def get_inspector_overview(novel_id: str = Query(default=DEFAULT_NOVEL_ID,
                                                     min_length=3, max_length=96)
                               ) -> dict[str, Any]:
        """M15-01 Canon Inspector：各层数量与出处摘要（只读）。"""

        return inspector_overview(project_root, novel_id)

    @router.get("/inspector/search")
    def get_inspector_search(novel_id: str = Query(default=DEFAULT_NOVEL_ID,
                                                   min_length=3, max_length=96),
                             query: str = Query(default="", max_length=120),
                             layer: str = Query(default="", max_length=32),
                             record_kind: str = Query(default="", max_length=32),
                             limit: int = Query(default=50, ge=1, le=200)
                             ) -> dict[str, Any]:
        """M15-01：跨层检索（Canon 事实 / 实体 / StoryState / 570 章 historical IR）。"""

        return inspector_search(project_root, novel_id, query=query, layer=layer,
                                record_kind=record_kind, limit=limit)

    @router.get("/inspector/record")
    def get_inspector_record(novel_id: str = Query(default=DEFAULT_NOVEL_ID,
                                                   min_length=3, max_length=96),
                             ref_id: str = Query(min_length=1, max_length=128)
                             ) -> dict[str, Any]:
        """M15-01：单条记录 + provenance / lineage（只读）。"""

        return inspector_record(project_root, novel_id, ref_id=ref_id)

    @router.get("/repair/diagnosis")
    def get_repair_diagnosis(novel_id: str = Query(default=DEFAULT_NOVEL_ID,
                                                   min_length=3, max_length=96)
                             ) -> dict[str, Any]:
        """M15-02 Repair Center：诊断（问题 / 证据 / 建议动作 / 审批要求 / 影响），只读。"""

        return repair_diagnosis(project_root, novel_id)

    @router.get("/repair/history")
    def get_repair_history(novel_id: str = Query(default=DEFAULT_NOVEL_ID,
                                                 min_length=3, max_length=96)
                           ) -> dict[str, Any]:
        """M15-02：修复历史 / effect log（只读）。"""

        return repair_history(project_root, novel_id)

    @router.get("/writer/context")
    def get_writer_context(novel_id: str = Query(default=DEFAULT_NOVEL_ID,
                                                 min_length=3, max_length=96),
                           branch_id: str = Query(default=DEFAULT_BRANCH, max_length=80),
                           chapter_id: str = Query(default="", max_length=128),
                           event_id: str = Query(default="", max_length=128)
                           ) -> dict[str, Any]:
        """M16B：分层 writer context（canon / occurred / repair / planned / guidance）。"""

        return WriterContextBuilder(project_root, novel_id).build(
            branch_id=branch_id, chapter_id=chapter_id, event_id=event_id)

    @router.post("/writer/drafts", status_code=201)
    def post_writer_draft(body: WriterDraftRequest) -> dict[str, Any]:
        """M16B：writer 产品入口（生成 preview 草稿 + 既有事实校验）。"""

        return WriterDraftService(project_root, body.novel_id).create_draft(
            branch_id=body.branch_id, chapter_id=body.chapter_id, event_id=body.event_id,
            claims=body.claims, new_facts=body.new_facts, narration=body.narration,
            style=body.style)

    @router.get("/writer/drafts")
    def get_writer_drafts(novel_id: str = Query(default=DEFAULT_NOVEL_ID,
                                                min_length=3, max_length=96)
                          ) -> dict[str, Any]:
        service = WriterDraftService(project_root, novel_id)
        return {"novel_id": novel_id, "drafts": service.list_drafts(),
                "read_only": True}

    @router.get("/writer/drafts/{draft_id}")
    def get_writer_draft(draft_id: str,
                         novel_id: str = Query(default=DEFAULT_NOVEL_ID,
                                               min_length=3, max_length=96)
                         ) -> dict[str, Any]:
        return WriterDraftService(project_root, novel_id).get_draft(draft_id)

    @router.post("/writer/drafts/{draft_id}/sync-facts")
    def post_writer_sync_facts(draft_id: str,
                               novel_id: str = Query(default=DEFAULT_NOVEL_ID,
                                                     min_length=3, max_length=96)
                               ) -> dict[str, Any]:
        """M16B Draft Fact Sync：只产生 proposal，不写 StoryState / Canon。"""

        return WriterDraftService(project_root, novel_id).sync_facts(draft_id)

    @router.get("/catalogs")
    def get_catalog() -> dict[str, Any]:
        return index.catalog.model_dump(mode="json")

    @router.get("/steps/{step_id}")
    def get_step(step_id: StoryStep) -> dict[str, Any]:
        return {
            "step": index.require_step(step_id).model_dump(mode="json"),
            "options": [
                option.model_dump(mode="json") for option in index.options_for_step(step_id)
            ],
        }

    @router.post("/sessions", status_code=201)
    def create_session(body: CreateSessionRequest) -> dict[str, Any]:
        session = repository.create(body.project_id, session_id=body.session_id, entry_step=StoryStep(body.entry_step))
        return session_payload(session.session_id)

    @router.get("/sessions")
    def list_sessions(project_id: str = Query(min_length=3, max_length=96)):
        return {"sessions": [{"session_id": session.session_id, "created_at": session.created_at.isoformat(),
            "label": next((index.require_option(item.option_id).name if item.option_id else item.custom_text[:60]
                           for item in session.selections if item.step == StoryStep.WORLDVIEW), '未设定世界'),
            "selection_version": session.selection_version} for session in repository.list_for_project(project_id)]}

    @router.get("/sessions/latest")
    def latest_session(project_id: str = Query(min_length=3, max_length=96)) -> dict[str, Any]:
        session = repository.latest_for_project(project_id)
        if session is None:
            raise HTTPException(status_code=404, detail={"message": "当前项目还没有构筑会话"})
        return session_payload(session.session_id)

    @router.get("/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, Any]:
        return session_payload(session_id)

    @router.post("/sessions/{session_id}/selections")
    def set_selections(session_id: str, body: SetSelectionsRequest) -> dict[str, Any]:
        session = manager.set_step_selections(
            session_id,
            body.step,
            option_ids=body.option_ids,
            custom_texts=body.custom_texts,
            expected_selection_version=body.expected_selection_version,
            option_source=body.option_source,
        )
        return session_payload(session.session_id)

    @router.post("/sessions/{session_id}/back")
    def go_back(session_id: str, body: BackRequest) -> dict[str, Any]:
        session = manager.go_back(
            session_id,
            body.target_step,
            expected_selection_version=body.expected_selection_version,
        )
        return session_payload(session.session_id)

    @router.post("/sessions/{session_id}/recommendations")
    def recommend(session_id: str, body: RecommendationRequest) -> dict[str, Any]:
        session = repository.load(session_id)
        selected_ids = [item.option_id for item in session.selections if item.option_id]
        custom: dict[StoryStep, list[str]] = {}
        for selection in session.selections:
            if selection.custom_text:
                custom.setdefault(selection.step, []).append(selection.custom_text)
        result = recommendations.recommend(
            body.step or session.current_step,
            selected_ids,
            based_on_version=session.selection_version,
            custom_selections=custom,
            limit=body.limit,
            allow_entry=not session.selections and (body.step or session.current_step) == session.current_step,
        )
        # 推荐是派生结果，不回写会话，避免覆盖并行提交的蓝图状态或导航。
        session = session.model_copy(update={"recommendation_version": session.selection_version})
        return {
            "session": session.model_dump(mode="json"),
            "recommendation": result.model_dump(mode="json"),
        }

    @router.post("/sessions/{session_id}/save")
    def save_session(session_id: str, body: SaveSessionRequest) -> dict[str, Any]:
        session = repository.load(session_id)
        if session.selection_version != body.expected_selection_version:
            raise StorySessionError(
                "SESSION_VERSION_CONFLICT",
                "会话已在其他位置更新，请刷新后重试",
                session_id=session_id,
            )
        saved = repository.save(
            session,
            expected_selection_version=body.expected_selection_version,
        )
        return {"saved": True, **session_payload(saved.session_id)}

    @router.get("/sessions/{session_id}/history")
    def session_history(session_id: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "versions": [
                item.model_dump(mode="json") for item in repository.history_for(session_id)
            ],
        }

    @router.post("/sessions/{session_id}/compile-blueprint")
    def compile_blueprint(session_id: str) -> dict[str, Any]:
        return {"blueprint": blueprint_compiler.compile(session_id).model_dump(mode="json")}

    @router.get("/sessions/{session_id}/blueprint")
    def latest_blueprint(session_id: str) -> dict[str, Any]:
        blueprint = blueprint_repository.latest_for_session(session_id)
        if blueprint is None:
            raise StoryBlueprintError("BLUEPRINT_NOT_FOUND", "当前会话还没有故事蓝图")
        return {"blueprint": blueprint.model_dump(mode="json")}

    @router.post("/blueprints/{blueprint_id}/confirm")
    def confirm_blueprint(blueprint_id: str, body: ConfirmBlueprintRequest) -> dict[str, Any]:
        return {
            "blueprint": blueprint_compiler.confirm(blueprint_id, body.version).model_dump(mode="json")
        }

    @router.post("/blueprints/{blueprint_id}/outlines/{level}")
    def compile_outline(
        blueprint_id: str, level: OutlineLevel, body: CompileOutlineRequest
    ) -> dict[str, Any]:
        package = outline_compiler.compile(
            blueprint_id, body.blueprint_version, level, regenerate=body.regenerate
        )
        return {"outline": package.model_dump(mode="json")}

    @router.get("/blueprints/{blueprint_id}/outlines")
    def outline_chain(blueprint_id: str) -> dict[str, Any]:
        return {
            "outlines": [
                package.model_dump(mode="json") for package in outline_compiler.latest_chain(blueprint_id)
            ]
        }

    @router.post("/outlines/{package_id}/confirm")
    def confirm_outline(package_id: str, body: ConfirmOutlineRequest) -> dict[str, Any]:
        return {"outline": outline_compiler.confirm(package_id, body.version).model_dump(mode="json")}

    @router.post("/sessions/{session_id}/design/{field_id}")
    def choose_design(session_id: str, field_id: str, body: DesignChoiceRequest):
        save_design(index, repository, session_id, field_id, body.expected_selection_version,
                    body.option_id, body.custom_text)
        return session_payload(session_id)

    @router.put("/outlines/{package_id}/items/{item_id}")
    def edit_outline(package_id: str, item_id: str, body: EditOutlineRequest):
        package = outline_compiler.edit_item(package_id, body.expected_version, item_id, body.changes.model_dump(exclude_none=True))
        return {"outline": package.model_dump(mode='json')}

    @router.get("/outlines/{package_id}/export")
    def export_outline(package_id: str, version: int = Query(ge=1)):
        package = outline_repository.effective(outline_repository.load(package_id, version))
        return {"filename": f"故事大纲_{package.level.value}_V{version}.md", "content": outline_compiler.export_markdown(package)}

    return router


def install_story_builder_api(
    app: FastAPI,
    project_root: Path,
    *,
    catalog: StoryCatalogIndex | None = None,
    provider: Any | None = None,
) -> None:
    """将故事构筑路由和中文错误响应一起安装到 FastAPI 应用。"""

    app.include_router(
        create_story_builder_router(project_root, catalog=catalog, provider=provider)
    )

    async def handle_session_error(_request, exc: StorySessionError):
        status = 404 if exc.code == "SESSION_NOT_FOUND" else 409 if "CONFLICT" in exc.code else 422
        return JSONResponse(status_code=status, content={"detail": exc.as_dict()})

    async def handle_catalog_error(_request, exc: StoryCatalogError):
        return JSONResponse(status_code=422, content={"detail": exc.as_dict()})

    async def handle_blueprint_error(_request, exc: StoryBlueprintError):
        status = 404 if exc.code == "BLUEPRINT_NOT_FOUND" else 409 if "STALE" in exc.code else 422
        return JSONResponse(status_code=status, content={"detail": exc.as_dict()})

    async def handle_outline_error(_request, exc: StoryOutlineError):
        status = 404 if exc.code == "OUTLINE_NOT_FOUND" else 409 if "STALE" in exc.code else 422
        return JSONResponse(status_code=status, content={"detail": exc.as_dict()})

    async def handle_profile_error(_request, exc: NovelProfileError):
        status = 404 if exc.code == "PROFILE_NOT_FOUND" else 409 if exc.code == "PROFILE_EXISTS" else 422
        return JSONResponse(status_code=status, content={"detail": exc.as_dict()})

    async def handle_template_error(_request, exc: GenreTemplateError):
        return JSONResponse(status_code=422, content={"detail": exc.as_dict()})

    async def handle_novel_admin_error(_request, exc: NovelAdminError):
        status = 404 if exc.code == "PROFILE_NOT_FOUND" else 422
        return JSONResponse(status_code=status, content={"detail": exc.as_dict()})

    app.add_exception_handler(StorySessionError, handle_session_error)
    app.add_exception_handler(StoryCatalogError, handle_catalog_error)
    app.add_exception_handler(StoryBlueprintError, handle_blueprint_error)
    app.add_exception_handler(StoryOutlineError, handle_outline_error)
    app.add_exception_handler(NovelProfileError, handle_profile_error)
    app.add_exception_handler(GenreTemplateError, handle_template_error)
    app.add_exception_handler(NovelAdminError, handle_novel_admin_error)
