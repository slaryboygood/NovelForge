"""Memory 测试 fixture（确定性、零网络、零真实模型）。

构造两本最小作品（Novel A / Novel B），使用**相同**的角色名与关键词，
以便验证 §31 的跨作品隔离（"名字一样也不许串"）。
"""

from __future__ import annotations

from pathlib import Path

from novelforge.memory import (
    AuthorPreferenceService,
    MemoryService,
    build_default_service,
)

CHARACTERS = ("hero", "rival")


def _write_profile_and_pack(root: Path, novel_id: str, title: str) -> str:
    from novelforge.story_engine.creative import CreativeBrief, save_creative_brief
    from novelforge.story_engine.profile import NovelProfileRepository
    from novelforge.story_engine.settings_gen import (
        content_pack_draft,
        default_pack_id,
        deterministic_seed,
        validate_pack_draft,
        write_content_pack,
    )

    repository = NovelProfileRepository(root)
    repository.create(novel_id, title=title)
    brief = CreativeBrief(original_idea=f"{title}：一个只属于 {novel_id} 的开局创意。",
                          tone="冷峻写实")
    save_creative_brief(root, novel_id, brief)
    seed = deterministic_seed(brief)
    pack_id = default_pack_id(novel_id)
    pack = validate_pack_draft(content_pack_draft(seed, pack_id=pack_id, brief=brief))
    write_content_pack(root, pack)
    return pack_id


def _write_canon(root: Path, novel_id: str, *, fact_text: str) -> int:
    from novelforge.persistence.paths import canon_db_path
    from novelforge.story_engine.canon.models import CanonEntity, CanonFact
    from novelforge.story_engine.canon.repository import CanonRepository

    path = canon_db_path(root, novel_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    repository = CanonRepository(path)
    try:
        repository.save_fact(CanonFact(
            fact_id="FACT_WEAPON_RULE", canonical_key="WEAPON_RULE",
            novel_id=novel_id, status="happened",
            canonical_description=fact_text))
        repository.save_entity(CanonEntity(
            entity_id="ENT_HERO", canonical_key="HERO", novel_id=novel_id,
            kind="character", display_name="主角"))
    finally:
        repository.close()
    return 1


def _write_state(root: Path, novel_id: str, *, injury: bool = True) -> int:
    from novelforge.story_engine.entities import Character, ResourceStock
    from novelforge.story_engine.state import EffectRecord, StoryState
    from novelforge.story_engine.storage import StoryStateRepository

    state = StoryState(novel_id=novel_id)
    state.timeline.tick = 3
    state.timeline.current_time = "第三天清晨"
    state.location.current = "station"
    state.location.known["station"] = __import__(
        "novelforge.story_engine.entities", fromlist=["Location"]).Location(
        id="station", name="中转站", kind="site")
    state.characters["hero"] = Character(id="hero", kind="player", name="主角")
    state.characters["rival"] = Character(id="rival", kind="npc", name="对手")
    state.resources["medkit"] = ResourceStock(id="medkit", amount=1, unit="份")
    state.knowledge.append(__import__(
        "novelforge.story_engine.entities", fromlist=["KnowledgeEntry"]).KnowledgeEntry(
        id="core_record", certainty="fact", holders=["hero"], reader_visible=True,
        source="act_probe", source_event="act_probe", tick=2))
    state.promises.append(__import__(
        "novelforge.story_engine.entities", fromlist=["PromiseState"]).PromiseState(
        id="promise_power", description="修复中转站的备用电源", debtor="hero",
        creditor="rival", status="open", created_tick=1, due_tick=5))
    state.effect_log.extend([
        EffectRecord(id="EF_1", order=1, op="change_relationship", entity="rival",
                     target="hero", value=-2, source="act_betray",
                     data={"tick": 2, "reason": "背叛"}),
        EffectRecord(id="EF_2", order=2, op="add_knowledge", entity="hero",
                     target="core_record", value=1, source="act_probe",
                     data={"tick": 3}),
    ])
    if injury:
        state.flags["hero_injured"] = True
    repository = StoryStateRepository(root)
    repository.save(state, f"runtime_{novel_id}", 1)
    return len(state.effect_log)


def build_novel(root: Path, novel_id: str, *, title: str, fact_text: str,
                injury: bool = True) -> dict[str, object]:
    pack_id = _write_profile_and_pack(root, novel_id, title)
    facts = _write_canon(root, novel_id, fact_text=fact_text)
    effects = _write_state(root, novel_id, injury=injury)
    return {"novel_id": novel_id, "pack_id": pack_id, "facts": facts,
            "effects": effects}


def build_two_novels(tmp_path: Path) -> tuple[str, str]:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划",
                fact_text="主角不会使用枪械")
    build_novel(tmp_path, "novel_beta", title="贝塔计划",
                fact_text="主角不会使用枪械")  # 故意同名同规则
    return "novel_alpha", "novel_beta"


def service_for(tmp_path: Path, novel_id: str, *,
                with_preferences: bool = True) -> MemoryService:
    preferences = None
    if with_preferences:
        preferences = AuthorPreferenceService(novel_id, project_root=tmp_path,
                                              project_id=novel_id)
    service = build_default_service(novel_id, tmp_path, preferences=preferences)
    service.rebuild()
    return service


__all__ = ["CHARACTERS", "build_novel", "build_two_novels", "service_for"]


class _StubProvider:
    """测试用 provider（零网络）：按脚本返回文本。"""

    def __init__(self, provider_id: str, script: list[str]) -> None:
        self.provider_id = provider_id
        self.script = list(script)
        self.calls = 0

    def complete(self, request: Any) -> Any:
        from novelforge.ai import ProviderResponse

        self.calls += 1
        text = self.script.pop(0) if self.script else ""
        return ProviderResponse(text=text, model=request.model,
                                usage_raw={"prompt_tokens": 3, "completion_tokens": 2})


def build_fake_gateway(script: list[str], *, provider_id: str = "stub",
                       model_id: str = "stub-model") -> tuple[Any, _StubProvider]:
    """构造只连 StubProvider 的 LLMGateway（memory 测试用，零网络）。"""

    from novelforge.ai import (
        InMemoryCache,
        LLMGateway,
        ModelRouter,
        ModelSpec,
        ProviderConfig,
        ProviderRegistry,
    )

    config = ProviderConfig(provider_id=provider_id, kind="openai_compatible",
                            base_url="http://stub.local/v1",
                            api_key_env="STUB_KEY", enabled=True,
                            default_model=model_id,
                            models=(ModelSpec(model_id=model_id,
                                              capabilities=("utility",
                                                            "structured_output"),
                                              cost_tier=1, speed_tier=1),))
    provider = _StubProvider(provider_id, script)
    gateway = LLMGateway({provider_id: provider},
                         router=ModelRouter(ProviderRegistry([config])),
                         cache=InMemoryCache(), sleep=lambda _s: None,
                         clock=lambda: 0.0)
    return gateway, provider


__all__ = ["CHARACTERS", "build_fake_gateway", "build_novel", "build_two_novels",
           "service_for"]
