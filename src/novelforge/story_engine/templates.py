"""Genre Template：题材模板（主计划 T06e）。

模板只提供“默认目录、推荐项与规则”，不是小说事实：

- 模板可以写入 Novel Profile 的目录与规则；
- 模板不会创建角色知识、资源库存、已发生事件或任何 StoryState 事实；
- 模板不覆盖作者已经写下的内容；
- 引擎不判断 genre 名称，只按照 concepts / catalogs / rules 的通用结构工作。

因此新增一个题材只需要新增一份模板数据，不需要修改核心算法。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from novelforge.models import StrictModel

from .entities import Ability, Faction, ResourceDefinition, StateEntry
from .profile import NovelProfile

GENERIC_CONCEPTS = ("progression", "resource", "faction", "identity", "ability", "location")


class GenreTemplateError(ValueError):
    """题材模板查找失败。"""

    def __init__(self, code: str, message: str, *, template_id: str = "") -> None:
        self.code = code
        self.message = message
        self.template_id = template_id
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "template_id": self.template_id}


class GenreTemplate(StrictModel):
    template_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    name: str = Field(min_length=1, max_length=60)
    genre: str = Field(default="", max_length=64)
    concepts: dict[str, list[str]] = Field(default_factory=dict)
    resource_catalog: dict[str, ResourceDefinition] = Field(default_factory=dict)
    ability_catalog: dict[str, Ability] = Field(default_factory=dict)
    factions: dict[str, Faction] = Field(default_factory=dict)
    rules: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _default_entry(entry: StateEntry, template_id: str) -> dict[str, Any]:
    data = dict(entry.data)
    data.setdefault("source", template_id)
    data.setdefault("default", True)
    return data


def apply_template(profile: NovelProfile, template_id: str) -> NovelProfile:
    """把模板作为默认目录合并进 Novel Profile，已有内容保持不动。"""

    if not template_id:
        return profile
    template = get_template(template_id)
    concepts = dict(profile.world_profile.get("concepts", {}))
    for concept, values in template.concepts.items():
        concepts.setdefault(concept, list(values))
    world_profile = dict(profile.world_profile)
    world_profile["concepts"] = concepts
    world_profile.setdefault("template", template_id)

    resources = dict(profile.resource_catalog)
    for key, value in template.resource_catalog.items():
        resources.setdefault(key, value.model_copy(update={"data": _default_entry(value, template_id)}))
    abilities = dict(profile.ability_catalog)
    for key, value in template.ability_catalog.items():
        abilities.setdefault(key, value.model_copy(update={"data": _default_entry(value, template_id)}))
    factions = dict(profile.factions)
    for key, value in template.factions.items():
        factions.setdefault(key, value.model_copy(update={"data": _default_entry(value, template_id)}))
    rules = list(profile.story_rules)
    rules.extend(rule for rule in template.rules if rule not in rules)
    return profile.model_copy(update={
        "template_id": template_id,
        "world_profile": world_profile,
        "resource_catalog": resources,
        "ability_catalog": abilities,
        "factions": factions,
        "story_rules": rules,
    })


XIANXIA_TEMPLATE = GenreTemplate(
    template_id="xianxia",
    name="修仙",
    genre="xianxia",
    concepts={
        "progression": ["境界"],
        "resource": ["灵石"],
        "faction": ["宗门"],
        "identity": ["弟子身份"],
        "ability": ["功法", "神通"],
        "location": ["秘境"],
    },
    resource_catalog={"spirit_stone": ResourceDefinition(id="spirit_stone", name="灵石", unit="枚")},
    ability_catalog={"technique": Ability(id="technique", kind="功法", name="功法",
                                          limits=["需要修为与材料"])},
    factions={"sect": Faction(id="sect", kind="sect", name="宗门", stance="控制修炼资源的分配")},
    rules=["获得必有交换：资源与身份都要有来源。",
           "境界突破需要过程与代价，不能凭一次选择直接跃升。"],
    notes=["模板只提供默认目录，是否拥有灵石与功法仍由剧情决定。"],
)

SCI_FI_TEMPLATE = GenreTemplate(
    template_id="sci_fi",
    name="科幻",
    genre="sci_fi",
    concepts={
        "progression": ["科技等级"],
        "resource": ["能源", "算力"],
        "faction": ["国家", "公司", "AI阵营"],
        "identity": ["权限身份"],
        "ability": ["义体", "AI", "基因能力"],
        "location": ["星球", "空间站", "舰船"],
    },
    resource_catalog={"energy": ResourceDefinition(id="energy", name="能源", unit="千瓦时"),
                      "compute": ResourceDefinition(id="compute", name="算力", unit="单元")},
    ability_catalog={"cyberware": Ability(id="cyberware", kind="义体", name="义体功能",
                                          limits=["需要能源与维护"])},
    factions={"corporation": Faction(id="corporation", kind="corporation", name="公司",
                                     stance="垄断能源与权限")},
    rules=["能源与算力有配额，升级需要维护成本。",
           "权限决定能接触的信息与场所。"],
    notes=["模板只提供默认目录，能源与算力库存仍由剧情决定。"],
)

TEMPLATES: dict[str, GenreTemplate] = {
    XIANXIA_TEMPLATE.template_id: XIANXIA_TEMPLATE,
    SCI_FI_TEMPLATE.template_id: SCI_FI_TEMPLATE,
}


def get_template(template_id: str) -> GenreTemplate:
    try:
        return TEMPLATES[template_id]
    except KeyError as exc:
        raise GenreTemplateError("TEMPLATE_NOT_FOUND", "找不到这个题材模板", template_id=template_id) from exc


def list_templates() -> list[GenreTemplate]:
    return [TEMPLATES[key] for key in sorted(TEMPLATES)]
