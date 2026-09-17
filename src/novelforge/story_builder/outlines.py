from __future__ import annotations

import hashlib
import json
import os
import uuid
import threading
from functools import wraps
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from novelforge.models import StrictModel

from .blueprints import StoryBlueprintRepository
from .catalog import StoryCatalogIndex
from .adventures import AdventureEngine
from fastapi import HTTPException
from .models import (
    BlueprintStatus,
    OutlineItem,
    OutlineLevel,
    OutlinePackage,
    OutlineStatus,
    StoryBlueprint,
    StoryStep,
)


DEFAULT_OUTLINES_PATH = Path("novel/authoring/story_builder/outlines")
OUTLINE_ORDER = (OutlineLevel.BOOK, OutlineLevel.VOLUME, OutlineLevel.ARC, OutlineLevel.CHAPTER)
_OUTLINE_LOCK = threading.RLock()


def _outline_locked(method):
    @wraps(method)
    def guarded(*args, **kwargs):
        with _OUTLINE_LOCK:
            return method(*args, **kwargs)
    return guarded


def route_digest(state: dict) -> str:
    return hashlib.sha256(json.dumps(state, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def apply_narrative_design(blueprint, items):
    """作者设计只影响写法和待安排目标，不能覆盖已发生的路线事实。"""
    fields = ('story_scope', 'theme_question', 'hero_false_belief', 'narrative_order', 'ending_direction',
              'world_rule', 'livelihood', 'location_access', 'ability_learning', 'ability_cost',
              'companion_boundary', 'relationship_tension', 'opponent_boundary', 'information_release',
              'main_thread', 'subplot_role', 'payoff_schedule')
    notes = [blueprint.design_summaries[key] + '；' + blueprint.design_effects.get(key, {}).get('planning', '自定义方向，具体场景安排待作者确认。')
             for key in fields if key in blueprint.design_summaries]
    pov = blueprint.design_effects.get('narrative_pov', {}).get('pov')
    if not pov and 'narrative_pov' in blueprint.design_summaries:
        pov = blueprint.design_summaries['narrative_pov'] + '（自定义，须逐场确认知识边界）'
    for item in items:
        if pov:
            item.pov = pov
        item.must_keep.extend('作者设计要求（非已发生事实）：' + note for note in notes)
    return items


def future_design_questions(blueprint):
    effects = blueprint.design_effects.get('main_thread', {})
    return ['未来阶段建议（未发生，待安排）：' + effects[key]
            for key in ('phase_1', 'phase_2', 'phase_3') if key in effects]


def route_items(blueprint, level, history):
    if level in (OutlineLevel.BOOK, OutlineLevel.VOLUME):
        groups = [history]
    elif level == OutlineLevel.ARC:
        groups = [history[:3]] + ([history[3:]] if len(history) > 3 else [])
    else:
        groups = [[entry] for entry in history]
    result, offset = [], 0
    for index, entries in enumerate(groups, 1):
        start = history[offset - 1]['result'] if offset else next(section.summary for section in blueprint.sections if section.step == StoryStep.BACKGROUND)
        title = {OutlineLevel.BOOK: '所选路线主线', OutlineLevel.VOLUME: '第一阶段 · 当前旅程', OutlineLevel.ARC: f'建议篇章 {index}', OutlineLevel.CHAPTER: f'建议第 {index} 章 · {entries[0]["scene"]}'}[level]
        if level == OutlineLevel.BOOK:
            children = ['route_volume_01']
        elif level == OutlineLevel.VOLUME:
            children = ['route_arc_01'] + (['route_arc_02'] if len(history) > 3 else [])
        elif level == OutlineLevel.ARC:
            children = [f'route_chapter_{n:02d}' for n in range(offset + 1, offset + len(entries) + 1)]
        else:
            children = []
        result.append(OutlineItem(item_id=f'route_{level.value.lower()}_{index:02d}', title=title,
            summary='\n'.join(entry['choice'] + ' → ' + entry['result'] for entry in entries),
            start_state=start, end_state=entries[-1]['result'], goals=[entry['choice'] for entry in entries],
            conflicts=[entry.get('context', '旧记录未保存场景详情，待作者补充。') for entry in entries],
            major_turns=[entry['result'] for entry in entries],
            ending_hook=history[offset + len(entries)]['scene'] if offset + len(entries) < len(history) else '当前路线阶段收束，不擅自增加下一场冲突。',
            must_keep=[f'来源：路线第 {offset + n} 次选择；{entry["choice_id"]}' for n, entry in enumerate(entries, 1)],
            must_avoid=['不得混入未选择分支的事件或未核实的解释。'], child_ids=children))
        result[-1] = result[-1].model_copy(update={
            'pov': '建议采用主角限知视角，待作者确认。',
            'time': '故事起始时点，具体时间待定。' if offset == 0 else '承接上一场结果，具体间隔待定。',
            'location': '建议围绕' + blueprint.design_effects.get('home_region', {}).get('place', '当前故事地点') + '安排；具体场地待作者确认。',
            'participants': ['主角'] + (['协助者（姓名待定）'] if any(entry['choice_id'] in ('help', 'ally', 'rescue', 'honor_partner', 'negotiate_time') for entry in entries) else []),
            'costs': [entry.get('cost', '旧历史未记录具体代价，待补充。') for entry in entries],
            'information_changes': [entry['result'] for entry in entries if entry['choice_id'] in ('clue', 'seek_receipt', 'verify_order', 'record_limits')],
        })
        offset += len(entries)
    return apply_narrative_design(blueprint, result)


class StoryOutlineError(ValueError):
    def __init__(self, code: str, message: str, *, package_id: str = "") -> None:
        self.code = code
        self.message = message
        self.package_id = package_id
        super().__init__(message)

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "package_id": self.package_id}


class StoredOutlinePackage(StrictModel):
    schema_version: Literal[1] = 1
    package: OutlinePackage


class StoryOutlineRepository:
    def __init__(self, project_root: Path, outlines_path: Path | str = DEFAULT_OUTLINES_PATH):
        self.project_root = project_root.resolve()
        relative = Path(outlines_path)
        self.outlines_dir = (
            relative.resolve() if relative.is_absolute() else (self.project_root / relative).resolve()
        )
        try:
            self.outlines_dir.relative_to(self.project_root)
        except ValueError as exc:
            raise StoryOutlineError("OUTLINE_PATH_OUTSIDE_PROJECT", "大纲目录超出当前项目范围") from exc

    @_outline_locked
    def save(self, package: OutlinePackage) -> OutlinePackage:
        path = self.path_for(package.level, package.package_id, package.version)
        if path.exists():
            current = self.load(package.package_id, package.version)
            if current.status == OutlineStatus.CONFIRMED and current != package:
                raise StoryOutlineError(
                    "OUTLINE_CONFIRMED_IMMUTABLE", "已确认的大纲版本不能被覆盖", package_id=package.package_id
                )
        self._atomic_write(path, StoredOutlinePackage(package=package))
        return package

    @_outline_locked
    def load(self, package_id: str, version: int) -> OutlinePackage:
        matches = [
            self.path_for(level, package_id, version)
            for level in OUTLINE_ORDER
            if self.path_for(level, package_id, version).is_file()
        ]
        if len(matches) != 1:
            raise StoryOutlineError("OUTLINE_NOT_FOUND", "找不到大纲版本", package_id=package_id)
        try:
            raw = json.loads(matches[0].read_text(encoding="utf-8-sig"))
            package = StoredOutlinePackage.model_validate(raw).package
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise StoryOutlineError("OUTLINE_READ_FAILED", "无法读取大纲版本", package_id=package_id) from exc
        if package.package_id != package_id or package.version != version:
            raise StoryOutlineError("OUTLINE_ID_MISMATCH", "大纲文件名与内容不一致", package_id=package_id)
        return package

    def latest(self, level: OutlineLevel, package_id: str) -> OutlinePackage | None:
        folder = self.outlines_dir / level.value.lower() / package_id
        paths = sorted(folder.glob("v*.json")) if folder.exists() else []
        return self.load(package_id, int(paths[-1].stem[1:])) if paths else None

    def latest_confirmed(self, level: OutlineLevel, package_id: str) -> OutlinePackage | None:
        folder = self.outlines_dir / level.value.lower() / package_id
        paths = sorted(folder.glob("v*.json"), reverse=True) if folder.exists() else []
        for path in paths:
            package = self.load(package_id, int(path.stem[1:]))
            if package.status == OutlineStatus.CONFIRMED:
                return package
        return None

    def effective(self, package: OutlinePackage) -> OutlinePackage:
        if package.route_source:
            digest = self._route_digest(package)
            if digest is None or digest != package.route_source.get('digest'):
                return package.model_copy(update={"status": OutlineStatus.NEEDS_REVIEW})
        if package.level == OutlineLevel.BOOK:
            return package
        parent_level = OUTLINE_ORDER[OUTLINE_ORDER.index(package.level) - 1]
        for parent_id, source_version in package.source_package_versions.items():
            current = self.latest_confirmed(parent_level, parent_id)
            current_effective = self.effective(current) if current is not None else None
            if (
                current_effective is None
                or current_effective.status != OutlineStatus.CONFIRMED
                or current_effective.version != source_version
            ):
                return package.model_copy(update={"status": OutlineStatus.NEEDS_REVIEW})
        return package

    def _route_digest(self, package: OutlinePackage) -> str | None:
        """路线摘要：V1 蓝图路线走 Adventure；W3 小说级运行槽走 StoryState。

        两条路径都只读取事实，返回 None 表示来源不可读（按 NEEDS_REVIEW 处理）。
        """

        try:
            state = AdventureEngine(self.project_root).start(
                package.blueprint_id, package.blueprint_version,
                package.route_source.get('branch_id', 'main'))['state']
            return route_digest(state)
        except HTTPException:
            pass
        except Exception:  # noqa: BLE001 - 非蓝图槽不是错误，继续尝试运行槽
            pass
        try:
            from novelforge.story_engine.creator import runtime_key_for
            from novelforge.story_engine.outline_forge import state_digest
            from novelforge.story_engine.storage import StoryStateRepository

            states = StoryStateRepository(self.project_root)
            branch = package.route_source.get('branch_id', 'main')
            candidates = [package.blueprint_id]
            derived = runtime_key_for(package.blueprint_id)
            if derived not in candidates:
                candidates.append(derived)
            for slot in candidates:
                try:
                    state = states.load(slot, package.blueprint_version, branch)
                except Exception:  # noqa: BLE001 - 换下一个候选槽位
                    continue
                return state_digest(state)
            return None
        except Exception:  # noqa: BLE001 - 读取失败按来源失效处理
            return None

    def path_for(self, level: OutlineLevel, package_id: str, version: int) -> Path:
        if version < 1 or not package_id.startswith("ol_") or not package_id.replace("_", "").isalnum():
            raise StoryOutlineError("OUTLINE_ID_INVALID", "大纲 ID 或版本格式不正确", package_id=package_id)
        return self.outlines_dir / level.value.lower() / package_id / f"v{version:06d}.json"

    @staticmethod
    def _atomic_write(path: Path, document: StoredOutlinePackage) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        payload = json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


class StoryOutlineCompiler:
    def __init__(
        self,
        catalog: StoryCatalogIndex,
        blueprints: StoryBlueprintRepository,
        outlines: StoryOutlineRepository,
    ) -> None:
        self.catalog = catalog
        self.blueprints = blueprints
        self.outlines = outlines

    @_outline_locked
    def compile(
        self,
        blueprint_id: str,
        blueprint_version: int,
        level: OutlineLevel | str,
        *,
        regenerate: bool = False,
    ) -> OutlinePackage:
        level = OutlineLevel(level)
        blueprint = self.blueprints.load(blueprint_id, blueprint_version)
        if blueprint.status != BlueprintStatus.CONFIRMED:
            raise StoryOutlineError("OUTLINE_BLUEPRINT_NOT_CONFIRMED", "请先确认故事蓝图")
        package_id = outline_id(blueprint_id, level)
        latest = self.outlines.latest(level, package_id)
        if level == OutlineLevel.BOOK and latest and latest.route_source:
            state = AdventureEngine(self.outlines.project_root).start(blueprint_id, blueprint_version, latest.route_source['branch_id'])['state']
            return self.compile_route(blueprint_id, blueprint_version, latest.route_source['branch_id'], state['revision'], regenerate=regenerate)
        parent = self._parent(blueprint, level)
        sources = {parent.package_id: parent.version} if parent else {}
        if (
            latest
            and not regenerate
            and latest.blueprint_version == blueprint.version
            and latest.source_package_versions == sources
        ):
            return self.outlines.effective(latest)

        package = OutlinePackage(
            package_id=package_id,
            project_id=blueprint.project_id,
            blueprint_id=blueprint.blueprint_id,
            blueprint_version=blueprint.version,
            level=level,
            version=(latest.version + 1) if latest else 1,
            parent_package_id=parent.package_id if parent else None,
            items=self._items(blueprint, level, parent),
            source_package_versions=sources,
            route_source=parent.route_source if parent else {},
            route_history=parent.route_history if parent else [],
            design_sections=parent.design_sections if parent else blueprint.design_summaries,
            pending_questions=parent.pending_questions if parent else future_design_questions(blueprint),
        )
        return self.outlines.save(package)

    @_outline_locked
    def confirm(self, package_id: str, version: int) -> OutlinePackage:
        package = self.outlines.load(package_id, version)
        latest = self.outlines.latest(package.level, package_id)
        if latest and latest.version != version:
            raise StoryOutlineError('OUTLINE_VERSION_STALE', '已有更新的大纲版本，请刷新后确认', package_id=package_id)
        effective = self.outlines.effective(package)
        if effective.status == OutlineStatus.NEEDS_REVIEW:
            raise StoryOutlineError("OUTLINE_PARENT_STALE", "上层大纲已变化，请重新生成本层大纲", package_id=package_id)
        if package.route_source.get("runtime_id"):
            # W3 运行槽路线：没有故事蓝图，蓝图确认门禁不适用；其余规则完全一致。
            try:
                blueprint = self.blueprints.load(package.blueprint_id, package.blueprint_version)
            except Exception:  # noqa: BLE001 - 运行槽没有蓝图属于正常情况
                blueprint = None
            if blueprint is not None and blueprint.status != BlueprintStatus.CONFIRMED:
                raise StoryOutlineError("OUTLINE_BLUEPRINT_NOT_CONFIRMED", "故事蓝图尚未确认", package_id=package_id)
        else:
            blueprint = self.blueprints.load(package.blueprint_id, package.blueprint_version)
            if blueprint.status != BlueprintStatus.CONFIRMED:
                raise StoryOutlineError("OUTLINE_BLUEPRINT_NOT_CONFIRMED", "故事蓝图尚未确认", package_id=package_id)
        confirmed = package.model_copy(
            update={"status": OutlineStatus.CONFIRMED, "confirmed_by_author": True}
        )
        return self.outlines.save(confirmed)

    def latest_chain(self, blueprint_id: str) -> list[OutlinePackage]:
        result: list[OutlinePackage] = []
        for level in OUTLINE_ORDER:
            package = self.outlines.latest(level, outline_id(blueprint_id, level))
            if package:
                result.append(self.outlines.effective(package))
        return result

    def _parent(self, blueprint: StoryBlueprint, level: OutlineLevel) -> OutlinePackage | None:
        if level == OutlineLevel.BOOK:
            return None
        parent_level = OUTLINE_ORDER[OUTLINE_ORDER.index(level) - 1]
        parent_id = outline_id(blueprint.blueprint_id, parent_level)
        parent = self.outlines.latest_confirmed(parent_level, parent_id)
        if parent is None:
            raise StoryOutlineError(
                "OUTLINE_PARENT_NOT_CONFIRMED",
                f"请先确认{level_title(parent_level)}",
                package_id=outline_id(blueprint.blueprint_id, level),
            )
        return parent

    def _items(
        self,
        blueprint: StoryBlueprint,
        level: OutlineLevel,
        parent: OutlinePackage | None,
    ) -> list[OutlineItem]:
        if parent and parent.route_history:
            items = route_items(blueprint, level, parent.route_history)
            for item in items:
                relevant = [entry for entry in parent.items if item.item_id in entry.child_ids]
                item.must_keep.extend('上层计划：' + entry.title + '；' + entry.summary for entry in relevant)
            return items
        if level == OutlineLevel.BOOK:
            return apply_narrative_design(blueprint, self._book_items(blueprint))
        if level == OutlineLevel.VOLUME:
            return apply_narrative_design(blueprint, self._volume_items(blueprint))
        if level == OutlineLevel.ARC:
            return apply_narrative_design(blueprint, self._arc_items(blueprint, parent))
        return apply_narrative_design(blueprint, self._chapter_items(blueprint, parent))

    @_outline_locked
    def compile_route(self, blueprint_id: str, version: int, branch_id: str, expected_revision: int, *, regenerate=False):
        scene = AdventureEngine(self.outlines.project_root).start(blueprint_id, version, branch_id)
        state = scene['state']
        if state['revision'] != expected_revision:
            raise StoryOutlineError('OUTLINE_ROUTE_STALE', '路线进度已变化，请刷新后再整合')
        if not scene['completed'] or not state['history']:
            raise StoryOutlineError('OUTLINE_ROUTE_INCOMPLETE', '请先完成或收束当前阶段，再整合大纲')
        blueprint = self.blueprints.load(blueprint_id, version)
        source = {'branch_id': branch_id, 'revision': str(expected_revision), 'digest': route_digest(state)}
        package_id = outline_id(blueprint_id, OutlineLevel.BOOK)
        latest = self.outlines.latest(OutlineLevel.BOOK, package_id)
        if latest and latest.route_source == source and latest.blueprint_version == version and not regenerate:
            return latest
        sections = {section.step.value: section.summary for section in blueprint.sections}
        sections.update(blueprint.design_summaries)
        questions = ['当前路线只覆盖实际推演的阶段；全书规模与后续阶段仍须作者决定。', '章节切分是编辑建议，事件结果来自所选路线。']
        questions.extend(future_design_questions(blueprint))
        for key in ('story_scope', 'ending_direction'):
            if key in blueprint.design_summaries:
                questions.append('作者方向与实际路线的衔接待核对：' + blueprint.design_summaries[key])
        if 'diversion_verified' not in state.get('facts', []):
            questions.append('局部调拨谜题尚未核实，不得写成已经揭晓的事实。')
        if any('context' not in entry for entry in state['history']):
            questions.append('部分旧历史缺少场景原文，整理时保留缺项，不补造事实。')
        package = OutlinePackage(package_id=package_id, project_id=blueprint.project_id, blueprint_id=blueprint_id,
            blueprint_version=version, level=OutlineLevel.BOOK, version=latest.version + 1 if latest else 1,
            route_source=source, route_history=state['history'], design_sections=sections, pending_questions=questions,
            items=route_items(blueprint, OutlineLevel.BOOK, state['history']))
        return self.outlines.save(package)

    @_outline_locked
    def edit_item(self, package_id, expected_version, item_id, changes):
        package = self.outlines.load(package_id, expected_version)
        latest = self.outlines.latest(package.level, package_id)
        if not latest or latest.version != expected_version:
            raise StoryOutlineError('OUTLINE_VERSION_STALE', '大纲已更新，请刷新后再编辑')
        if self.outlines.effective(package).status == OutlineStatus.NEEDS_REVIEW:
            raise StoryOutlineError('OUTLINE_SOURCE_STALE', '来源已变化，请重新整合大纲后再编辑')
        allowed = {'title', 'summary', 'start_state', 'end_state', 'ending_hook', 'goals', 'conflicts', 'major_turns', 'pov', 'time', 'location', 'participants', 'information_changes', 'costs'}
        if not changes or set(changes) - allowed:
            raise StoryOutlineError('OUTLINE_EDIT_INVALID', '只能编辑正文设计内容，不能修改来源或层级关系')
        if not any(item.item_id == item_id for item in package.items):
            raise StoryOutlineError('OUTLINE_ITEM_NOT_FOUND', '找不到该大纲条目')
        items = [OutlineItem.model_validate({**item.model_dump(), **changes}) if item.item_id == item_id else item for item in package.items]
        updated = package.model_copy(update={'items': items, 'version': expected_version + 1, 'status': OutlineStatus.DRAFT, 'confirmed_by_author': False})
        return self.outlines.save(updated)


    def export_markdown(self, package):
        status = '已确认' if package.status == OutlineStatus.CONFIRMED else '候选 / 待复核'
        lines = [f'# 故事大纲 V{package.version}', '', f'状态：{status}', '', '## 设计来源', '']
        lines.extend(package.design_sections.values())
        if package.route_source:
            lines.extend(['', f"路线：{package.route_source['branch_id']}，选择次数：{package.route_source['revision']}"])
        for item in package.items:
            lines.extend(['', f'## {item.title}', '', item.summary])
            for title, value in [('起始', item.start_state), ('结果', item.end_state), ('视角', item.pov), ('时间', item.time), ('地点', item.location), ('衔接', item.ending_hook)]:
                if value:
                    lines.extend(['', f'### {title}', '', value])
            for title, values in [('出场', item.participants), ('目标', item.goals), ('冲突', item.conflicts), ('转折', item.major_turns), ('代价', item.costs), ('信息变化', item.information_changes), ('设计要求与来源', item.must_keep), ('避免', item.must_avoid)]:
                if values:
                    lines.extend(['', f'### {title}', ''] + ['- ' + value for value in values])
        lines.extend(['', '## 待决定事项', ''] + ['- ' + value for value in package.pending_questions])
        return '\n'.join(lines) + '\n'

    def _book_items(self, blueprint: StoryBlueprint) -> list[OutlineItem]:
        event = self._section(blueprint, StoryStep.MAJOR_EVENTS)
        progression = self._section(blueprint, StoryStep.PROGRESSION)
        boundaries = self._section(blueprint, StoryStep.AUTHOR_BOUNDARIES)
        return [
            OutlineItem(
                item_id="book_main",
                title="全书主线",
                summary=blueprint.premise,
                start_state=self._section(blueprint, StoryStep.BACKGROUND).summary,
                end_state=f"主角经历完整成长并对核心冲突作出自己的最终选择。{progression.summary}",
                goals=[event.summary, progression.summary],
                conflicts=[self._section(blueprint, StoryStep.FACTIONS_LOCATIONS).summary],
                major_turns=["从起始困境中获得行动能力", "进入更大社会并遭遇价值冲突", "在最终危机中主动决定故事的方向"],
                ending_hook="主角的最终选择回答开篇提出的核心问题。",
                must_keep=[boundaries.summary],
                child_ids=["volume_01", "volume_02", "volume_03"],
            )
        ]

    def _volume_items(self, blueprint: StoryBlueprint) -> list[OutlineItem]:
        phases = [
            ("建立与出发", "主角从起始困境中站稳，建立行动方式与第一批关系。", "主角主动踏入更大范围的冲突。"),
            ("扩张与反转", "世界、势力与成长代价全面扩大，早期成功经验开始失效。", "主角放弃一个曾经正确的答案，重新选择立场。"),
            ("对决与收束", "所有主要关系、能力与伏笔汇入终局冲突。", "主角承担最终选择的代价，完成主题回答。"),
        ]
        event = self._section(blueprint, StoryStep.MAJOR_EVENTS).summary
        return [
            OutlineItem(
                item_id=f"volume_{index:02d}", title=f"第{index}卷·{title}",
                summary=f"{summary}{event}",
                start_state="承接上一卷的人物、资源与未解问题。" if index > 1 else self._section(blueprint, StoryStep.BACKGROUND).summary,
                end_state=end,
                goals=[summary], conflicts=[self._section(blueprint, StoryStep.FACTIONS_LOCATIONS).summary],
                major_turns=["卷初具体行动", "卷中代价升级", "卷末不可逆选择"],
                ending_hook=end,
                must_keep=[self._section(blueprint, StoryStep.AUTHOR_BOUNDARIES).summary],
                child_ids=[f"arc_{index * 2 - 1:02d}", f"arc_{index * 2:02d}"],
            )
            for index, (title, summary, end) in enumerate(phases, 1)
        ]

    def _arc_items(self, blueprint: StoryBlueprint, parent: OutlinePackage | None) -> list[OutlineItem]:
        assert parent is not None
        items: list[OutlineItem] = []
        arc_index = 0
        for volume in parent.items:
            for half, purpose in enumerate(("建立问题并迫使主角行动", "扩大代价并以选择收束阶段"), 1):
                arc_index += 1
                start = f"承接{volume.title}当前状态，一个具体问题迫近。"
                end = f"第{arc_index}篇的问题得到阶段答案，同时留下通往下一篇的行动后果。"
                items.append(OutlineItem(
                    item_id=f"arc_{arc_index:02d}", title=f"A{arc_index:02d}·{volume.title.split('·')[-1]}之{half}",
                    summary=f"{purpose}。{volume.summary}", start_state=start, end_state=end,
                    goals=[purpose], conflicts=[self._section(blueprint, StoryStep.MAJOR_EVENTS).summary],
                    major_turns=["发现可行方向", "方案引发新代价", "主角作出阶段选择"],
                    ending_hook=end,
                    must_keep=[self._section(blueprint, StoryStep.STYLE).summary],
                    child_ids=[f"chapter_{number:03d}" for number in range((arc_index - 1) * 4 + 1, arc_index * 4 + 1)],
                ))
        return items

    def _chapter_items(self, blueprint: StoryBlueprint, parent: OutlinePackage | None) -> list[OutlineItem]:
        assert parent is not None
        beats = [
            ("接到问题", "主角看见危机或机会，必须立即决定是否行动。"),
            ("试探规则", "主角用已有能力尝试解决，并发现方案中的隐藏限制。"),
            ("代价升级", "尝试改变了局面，人物关系、资源或风险至少一项发生变化。"),
            ("作出选择", "主角不再被动接受结果，而是选择下一个具体行动目标。"),
        ]
        items: list[OutlineItem] = []
        chapter_number = 0
        for arc in parent.items:
            for beat_name, beat_summary in beats:
                chapter_number += 1
                next_action = f"第{chapter_number + 1}章将直接承接本章结果。" if chapter_number < len(parent.items) * 4 else "本阶段结果将交给后续大纲扩展。"
                items.append(OutlineItem(
                    item_id=f"chapter_{chapter_number:03d}", title=f"CH{chapter_number:03d}·{beat_name}",
                    summary=f"所属：{arc.title}。{beat_summary}", start_state=arc.start_state if beat_name == "接到问题" else "承接上一章实际发生的伤势、信息、位置、关系和资源变化。",
                    end_state=beat_summary,
                    goals=[beat_summary], conflicts=[arc.conflicts[0] if arc.conflicts else "当前问题阻碍主角行动。"],
                    major_turns=["明确本章目标", "具体阻碍改变方案", "结果改变下一章行动"],
                    ending_hook=next_action,
                    must_keep=["本章必须产生可追踪的状态变化。"],
                    must_avoid=["不能忽略上一章结尾重新开场。", self._section(blueprint, StoryStep.AUTHOR_BOUNDARIES).summary],
                ))
        return items

    @staticmethod
    def _section(blueprint: StoryBlueprint, step: StoryStep):
        return next(section for section in blueprint.sections if section.step == step)


def outline_id(blueprint_id: str, level: OutlineLevel) -> str:
    digest = hashlib.sha256(blueprint_id.encode("utf-8")).hexdigest()[:14]
    return f"ol_{level.value.lower()}_{digest}"


def level_title(level: OutlineLevel) -> str:
    return {
        OutlineLevel.BOOK: "全书大纲",
        OutlineLevel.VOLUME: "卷纲",
        OutlineLevel.ARC: "篇章纲",
        OutlineLevel.CHAPTER: "章纲",
    }[level]
