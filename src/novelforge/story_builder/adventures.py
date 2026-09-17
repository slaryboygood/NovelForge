from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import Field

from novelforge.models import StrictModel
from novelforge.story_engine import (
    JourneyRuntime,
    StoryStateRepository,
    StoryStateStorageError,
    design_from_blueprint,
    initial_journey_state,
    journey_revision,
    load_pack_from_project,
)
from .blueprints import StoryBlueprintRepository
from .sessions import StorySessionRepository
_ADVENTURE_LOCK = threading.RLock()
RUNTIME_RULES_VERSION = 3


def unparsed_warnings(blueprint):
    values = [text for section in blueprint.sections for text in section.custom_inputs]
    values.extend(value.custom_text for value in blueprint.design_choices.values() if value.custom_text)
    return ['以下自定义内容尚未被事件规则理解，只保存在蓝图中：' + '；'.join(values)] if values else []


def _choice_result(story) -> str:
    for record in reversed(story.effect_log):
        if record.op == "choice" and (record.data or {}).get("result"):
            return str(record.data["result"])
    return ""


class Adventure(StrictModel):
    blueprint_id: str
    blueprint_version: int
    revision: int = 0
    rules_version: Literal[1, 2, 3] = 1
    branch_id: str = Field(default="main", pattern=r"^(main|branch_[a-f0-9]{32})$")
    parent_branch: str | None = None
    fork_revision: int | None = None
    supplies: int = 2
    ally: bool = False
    clue: bool = False
    trust: int = 0
    debt: int = 0
    facts: list[str] = Field(default_factory=list)
    arc_finished: bool = False
    history: list[dict[str, str]] = Field(default_factory=list)


class AdventureEngine:
    """有界事件与历史分支。规则掌管后果，客户端只提交选项编号。"""

    def __init__(self, root: Path):
        self.root = root
        self.blueprints = StoryBlueprintRepository(root)
        self.sessions = StorySessionRepository(root)
        self.lock = _ADVENTURE_LOCK
        self.states = StoryStateRepository(root)
        try:
            self.pack = load_pack_from_project(root, self._pack_id_for_root(root))
        except Exception:  # noqa: BLE001 - 没有内容包时退回旧规则，保证旧功能可用
            self.pack = None
        self.runtime = JourneyRuntime(self.pack) if self.pack is not None else None

    @staticmethod
    def _pack_id_for_root(root: Path) -> str:
        """运行态内容包由小说实例决定；引擎只读配置，不判断题材。"""

        return "journey_v1"

    def _pack_id_for(self, blueprint) -> str:
        try:
            from novelforge.story_engine import NovelProfileRepository

            profile = NovelProfileRepository(self.root).load(blueprint.project_id)
            return profile.content_pack_id or self._pack_id_for_root(self.root)
        except Exception:  # noqa: BLE001 - 没有 profile 时使用默认包
            return self._pack_id_for_root(self.root)

    def _pack_for(self, blueprint):
        """按小说实例解析内容包；找不到时退回默认包。"""

        pack_id = self._pack_id_for(blueprint)
        if pack_id == getattr(self, "_active_pack_id", ""):
            return self.pack, self.runtime
        self._active_pack_id = pack_id
        try:
            pack = load_pack_from_project(self.root, pack_id)
        except Exception:  # noqa: BLE001
            pack = self.pack
        return pack, (JourneyRuntime(pack) if pack is not None else None)

    def _source(self, blueprint_id: str, version: int):
        blueprint = self.blueprints.load(blueprint_id, version)
        session = self.sessions.load(blueprint.source_session_id)
        if (blueprint.status != "CONFIRMED" or session.needs_review_steps
                or session.selection_version != blueprint.source_selection_version):
            raise HTTPException(409, "设定尚未确认或已经变化，请重新确认故事蓝图。")
        return blueprint

    def _path(self, blueprint_id: str, version: int, branch_id: str = "main") -> Path:
        # 先由蓝图仓库验证标识，不能让外部输入绕过路径校验。
        self.blueprints.path_for(blueprint_id, version)
        import re
        if not re.fullmatch(r"main|branch_[a-f0-9]{32}", branch_id):
            raise HTTPException(422, "路线编号无效")
        suffix = "" if branch_id == "main" else f"_{branch_id}"
        return self.root / "novel/authoring/story_builder/adventures" / blueprint_id / f"v{version:06d}{suffix}.json"

    def _save(self, state: Adventure):
        path = self._path(state.blueprint_id, state.blueprint_version, state.branch_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            with temp.open("w", encoding="utf-8") as stream:
                stream.write(state.model_dump_json(indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def start(self, blueprint_id: str, version: int, branch_id: str = "main"):
        with self.lock:
            blueprint = self._source(blueprint_id, version)
            pack, runtime = self._pack_for(blueprint)
            self.pack, self.runtime = pack, runtime
            path = self._path(blueprint_id, version, branch_id)
            if branch_id != "main" and not path.exists():
                raise HTTPException(404, "找不到这条故事路线")
            if path.exists():
                state = Adventure.model_validate_json(path.read_text(encoding="utf-8"))
            else:
                state = Adventure(blueprint_id=blueprint_id, blueprint_version=version,
                                  rules_version=RUNTIME_RULES_VERSION
                                  if self.runtime is not None
                                  else 2 if blueprint.design_choices else 1)
            if not path.exists():
                self._save(state)
            return self.view(state)

    def view(self, state: Adventure):
        blueprint = self._source(state.blueprint_id, state.blueprint_version)
        if state.rules_version == RUNTIME_RULES_VERSION and self.runtime is not None:
            return self._runtime_view(state, blueprint)
        if state.rules_version == 2:
            return self.design_scene(state, blueprint)
        ids = {item for section in blueprint.sections for item in section.selected_option_ids}
        place = "废弃能源站" if "world_silicon_mmo" in ids else "山门遗址" if "world_cultivation_realms" in ids else "封锁区旧驿站"
        place = blueprint.design_effects.get("home_region", {}).get("place", place)
        crisis = blueprint.design_choices.get("present_crisis")
        crisis_id = crisis.option_id if crisis else None
        if state.revision == 0:
            title, text = "第一关 · 岔路", f"通往{place}的道路塌了。碎石后传来求救声，另一侧散落着补给，墙角还留着一串新鲜记号。天色渐暗，你只能先处理一件事。"
            choices = [("help", "搬开碎石，救出引路人", "消耗 1 补给，获得同行者"), ("supply", "抢在封路前收集补给", "增加 2 补给，错过救援"), ("clue", "沿记号查明封路原因", "获得线索，独自前进")]
            if crisis_id == "crisis_quota":
                title, text = "第一关 · 被扣押的份额", f"{place}贴出了扣押通知。你的生活物资被留在封锁线内，申诉截止前必须找到依据。搬运时倒下的货架压住了一名知情人，他指着管理所的侧门。"
                choices = [("help", "支起货架，救出知情人", "消耗 1 补给，获得同行者"), ("clue", "留下扣押凭证，调查签发人", "获得证据，独自前进")]
            elif crisis_id == "crisis_missing":
                title, text = "第一关 · 失踪者的记号", f"你在{place}找到了失踪者留下的求助记号。一个被落石困住的旅人说，他见过那个人。另一串记号通往封锁区，天黑后就难以辨认。"
                choices = [("help", "救出目击者，请他带路", "消耗 1 补给，获得同行者"), ("clue", "先追查尚未消失的记号", "获得方向线索，独自前进")]
            elif crisis_id == "crisis_failure":
                title, text = "第一关 · 停摆前", f"{place}的维生设施正在停摆。维修通道被压住，值守者仍困在里面。旁边的备用箱还有物资，你必须决定先救人，还是先保住维修储备。"
                choices = [("help", "撑起维修通道，接应值守者", "消耗 1 补给，获得同行者"), ("supply", "先搬走备用箱里的补给", "增加 2 补给，失去救援时机")]
        elif state.revision == 1:
            title = "第二关 · 门前"
            text = f"{place}入口已被封住。" + ("你救下的人认出了侧门，愿意带路。" if state.ally else "守门人要你留下两份补给，才肯放行。")
            choices = [("wait", "绕过哨位，寻找排水道", "不消耗补给，但会惊动巡逻")]
            if state.ally:
                choices.insert(0, ("ally", "相信同行者，走侧门", "保留补给，建立信任"))
            if state.clue:
                choices.insert(0, ("proof", "出示记号，要求核查封锁令", "凭线索进入，留下姓名"))
            if state.supplies >= 2:
                choices.append(("pay", "交出两份补给，换取通行", "消耗 2 补给"))
        elif state.revision == 2:
            title, text = "第三关 · 代价", "你终于抵达中庭，却发现撤离通道即将关闭。封锁的证据就在控制室里，带走它意味着放弃眼前的安全出口。"
            if state.history[-1]["choice_id"] == "wait":
                text += "巡逻已经追到身后，你没有时间犹豫。"
            choices = [("leave", "保住现有收获，先撤离", "留下未解之谜，保存实力")]
            if state.ally or state.clue:
                choices.insert(0, ("expose", "与封锁者对峙，夺取证据", "已有的人脉或线索让这次冒险成为可能"))
            if state.supplies >= 1:
                choices.append(("rescue", "留下补给，接应被困者", "消耗 1 补给，获得新的盟友"))
        else:
            title, text = "本段旅程结束", state.history[-1]["result"]
            choices = []
        return {"state": state.model_dump(), "title": title, "text": text, "completed": state.revision == 3, "warnings": unparsed_warnings(blueprint),
                "choices": [{"id": key, "label": label, "cost": cost} for key, label, cost in choices]}

    # ---- 新引擎运行态（T08d-02b-2）----------------------------------

    def _load_story_state(self, state: Adventure, blueprint):
        try:
            return self.states.load(state.blueprint_id, state.blueprint_version, state.branch_id)
        except StoryStateStorageError:
            return initial_journey_state(self.pack, novel_id=blueprint.project_id)

    def _project(self, state: Adventure, story) -> Adventure:
        """把 StoryState 投影回既有 Adventure 形状，保持旧读者与前端可用。"""

        supplies = int(story.resources["supplies"].amount) if "supplies" in story.resources else 0
        return state.model_copy(update={
            "revision": journey_revision(story),
            "supplies": supplies,
            "ally": bool(story.flags.get("ally")),
            "clue": bool(story.flags.get("clue")),
            "trust": int(story.flags.get("trust", 0) or 0),
            "debt": int(story.flags.get("debt", 0) or 0),
            "facts": [item.id for item in story.knowledge],
            "arc_finished": bool(story.flags.get("arc_finished")),
        })

    def _scene_payload(self, state: Adventure, story, blueprint) -> dict:
        design = design_from_blueprint(blueprint)
        scene = self.runtime.scene(story, design, warnings=unparsed_warnings(blueprint))
        return {"state": self._project(state, story).model_dump(), "title": scene.title, "text": scene.text,
                "completed": scene.completed, "goal": scene.goal, "success": scene.success,
                "next_question": scene.next_question, "warnings": unparsed_warnings(blueprint),
                "choices": [{"id": item.id, "label": item.label, "cost": item.cost,
                             "suggested": item.suggested} for item in scene.choices]}

    def _runtime_view(self, state: Adventure, blueprint) -> dict:
        story = self._load_story_state(state, blueprint)
        self.states.save(story, state.blueprint_id, state.blueprint_version, state.branch_id)
        return self._scene_payload(state, story, blueprint)

    def _runtime_choose(self, state: Adventure, scene: dict, choice: dict) -> dict:
        blueprint = self._source(state.blueprint_id, state.blueprint_version)
        story = self._load_story_state(state, blueprint)
        design = design_from_blueprint(blueprint)
        result = self.runtime.choose(story, design, choice["id"])
        if not result.ok:
            raise HTTPException(422, result.message or "当前剧情不能选择这个行动。")
        mirrored = self._project(state, result.state).model_copy(update={
            "history": state.history + [{"scene": scene["title"], "context": scene["text"],
                                         "cost": choice["cost"], "choice_id": choice["id"],
                                         "choice": choice["label"],
                                         "result": _choice_result(result.state)}]})
        self.states.save(result.state, state.blueprint_id, state.blueprint_version, state.branch_id)
        self._save(mirrored)
        return self._scene_payload(mirrored, result.state, blueprint)

    def _runtime_fork(self, source: Adventure, parent: str, branch: str, at: int) -> Adventure:
        blueprint = self._source(source.blueprint_id, source.blueprint_version)
        design = design_from_blueprint(blueprint)
        story = initial_journey_state(self.pack, novel_id=blueprint.project_id)
        for entry in source.history[:at]:
            result = self.runtime.choose(story, design, entry["choice_id"])
            if not result.ok:
                raise HTTPException(422, result.message or "历史动作无法重放。")
            story = result.state
        state = self._project(source, story).model_copy(update={
            "branch_id": branch, "parent_branch": parent, "fork_revision": at,
            "history": source.history[:at]})
        self._save(state)
        self.states.save(story, source.blueprint_id, source.blueprint_version, branch)
        return state

    def choose(self, blueprint_id: str, version: int, revision: int, choice_id: str, branch_id: str = "main"):
        with self.lock:
            current = self.start(blueprint_id, version, branch_id)
            state = Adventure.model_validate(current["state"])
            if state.revision != revision:
                raise HTTPException(409, "进度已变化，请重新载入旅程后再选择。")
            choice = next((item for item in current["choices"] if item["id"] == choice_id), None)
            if choice is None:
                raise HTTPException(422, "当前剧情不能选择这个行动。")
            if state.rules_version == RUNTIME_RULES_VERSION and self.runtime is not None:
                return self._runtime_choose(state, current, choice)
            if state.rules_version == 2:
                return self.choose_design(state, current, choice)
            results = {
                "help": "你用补给撑起临时支架，救下了引路人。他指向遗址侧门。",
                "supply": "你带走四份补给。等你回头，求救声已经消失。",
                "clue": "你发现封锁令上的记号被人改过，留下了证据。",
                "ally": "引路人替你打开侧门。你们约定互相接应。",
                "proof": "守门人不敢销毁证据，放你进去，却记下了你的姓名。",
                "pay": "两份补给换来了通行，你剩下的储备更少了。",
                "wait": "你钻出排水道时触响了警铃。巡逻队开始搜寻入侵者。",
                "leave": "你及时撤出遗址，保住了收获。封锁者仍在，下一次必须准备得更充分。",
                "expose": "你带出了封锁证据，也成了对方追查的目标。下一段旅程将是护送证据。",
                "rescue": "你把最后的通行机会让给被困者。他们愿意同行，但所有人都需要新的补给。",
            }
            if state.revision == 0:
                # 后果只依赖本关实际发生的动作，不能把不同背景统一写成碎石救援。
                if choice_id == "help":
                    results["help"] = "你消耗一份补给，救出了被困者。他愿意带你去侧门，那里还没有封死。"
                elif choice_id == "clue":
                    results["clue"] = "你留下了现场证据，确定调查方向，但只能独自进入封锁区。"
                elif choice_id == "supply":
                    results["supply"] = "你收起两份补给。等你再回头，原来的救援通道已经完全封死。"
            state.supplies += {"help": -1, "supply": 2, "pay": -2, "rescue": -1}.get(choice_id, 0)
            state.ally = state.ally or choice_id in ("help", "rescue")
            state.clue = state.clue or choice_id in ("clue", "expose")
            state.history.append({"scene": current["title"], "choice_id": choice_id, "choice": choice["label"], "result": results[choice_id]})
            state.revision += 1
            self._save(state)
            return self.view(state)

    def fork(self, blueprint_id: str, version: int, parent: str, at: int, expected: int, request_id: str):
        with self.lock:
            source = Adventure.model_validate(self.start(blueprint_id, version, parent)["state"])
            branch = "branch_" + uuid.UUID(request_id).hex
            path = self._path(blueprint_id, version, branch)
            if path.exists():
                existing = Adventure.model_validate_json(path.read_text(encoding="utf-8"))
                if existing.parent_branch != parent or existing.fork_revision != at:
                    raise HTTPException(409, "这次请求已经用于另一个分支")
                return self.view(existing)
            if expected != source.revision:
                raise HTTPException(409, "原路线已经变化，请刷新后再创建分支")
            if at < 0 or at > source.revision:
                raise HTTPException(422, "不能从尚未发生的节点创建分支")
            if source.rules_version == RUNTIME_RULES_VERSION and self.runtime is not None:
                return self.view(self._runtime_fork(source, parent, branch, at))
            history = source.history[:at]
            actions = [item["choice_id"] for item in history]
            # 目前两版三关规则共用这些资源事务；未知动作必须先有明确重放规则。
            deltas = {"help": -1, "supply": 2, "clue": 0, "ally": 0, "proof": 0, "pay": -2, "wait": 0, "leave": 0, "expose": 0, "rescue": -1}
            deltas.update(FOLLOWUP_DELTAS)
            if any(action not in deltas for action in actions):
                raise HTTPException(409, "历史动作缺少重放规则，不能安全创建分支")
            state = source.model_copy(deep=True, update={"branch_id": branch, "parent_branch": parent, "fork_revision": at,
                "revision": at, "history": history, "supplies": 2 + sum(deltas[action] for action in actions),
                "ally": any(action in ("help", "rescue") for action in actions),
                "clue": any(action == "clue" or (source.rules_version == 1 and action == "expose") for action in actions),
                **followup_state(actions)})
            self._save(state)
            return self.view(state)

    def branches(self, blueprint_id: str, version: int):
        with self.lock:
            self._source(blueprint_id, version)
            main = self._path(blueprint_id, version)
            paths = [main] if main.exists() else []
            paths += sorted(main.parent.glob(f"v{version:06d}_branch_*.json"))
            result = []
            for path in paths:
                state = Adventure.model_validate_json(path.read_text(encoding="utf-8"))
                if (state.blueprint_id != blueprint_id or state.blueprint_version != version
                        or self._path(blueprint_id, version, state.branch_id) != path):
                    raise HTTPException(409, "路线文件与内容不一致，请检查存档")
                result.append({"branch_id": state.branch_id, "revision": state.revision,
                               "parent_branch": state.parent_branch, "fork_revision": state.fork_revision})
            return result

    def author_plan(self, blueprint_id: str, version: int):
        self._source(blueprint_id, version)
        return {"scope": "后续交接事件的局部谜题，不解释全书终局",
                "truth": "负责人将眼前一批物资改拨到另一急需点，但没有同步公开记录。",
                "plant": "先取得交接人保存的回执，发现日期相同而数量不同。",
                "verify": "选择核对原件，才能确认第二枚印记与留档相符。",
                "reveal": "只有 facts 包含 diversion_verified，才能选择公开核实证据。",
                "boundary": "角色和读者从实际事件获知；本页是作者视角，查看本页不会改变角色知识。"}

    def design_scene(self, state, blueprint):
        if state.revision >= 4:
            return self.followup_scene(state, blueprint)
        effects = blueprint.design_effects
        place = effects.get("home_region", {}).get("place")
        ids = {item for section in blueprint.sections for item in section.selected_option_ids}
        if not place:
            place = "山门驿站" if "world_cultivation_realms" in ids else "旧能源站" if "world_silicon_mmo" in ids else "街区办事处"
        chosen = lambda key: blueprint.design_choices[key].option_id if key in blueprint.design_choices else None
        pattern = chosen("opening_pattern") or {"crisis_failure": "opening_survival", "crisis_missing": "opening_mystery", "crisis_quota": "opening_disruption"}.get(chosen("present_crisis"), "opening_survival")
        profiles = {
            "opening_survival": ("出口即将关闭", "维生设施不断发出异响，安全出口已经开始关闭。", "撤出了危险区域", "安全设施为何会失效"),
            "opening_awakening": ("不在记录里", "你发现通行记录不承认你的身份，门外已经开始核对名单。", "核清了临时身份并离开限制区", "是谁留下了错误记录"),
            "opening_reversal": ("被拿走的成果", "你的成果被记在别人名下，签字的负责人正准备离开。", "保住了成果归属的证据", "谁在替冒领者撑腰"),
            "opening_trial": ("不一样的规则", "测试已经开始，你拿到的工具却比别人的少了一件。", "争取到了继续测试的条件", "测试真正要筛选的是什么"),
            "opening_mission": ("清单之外", "交接清单与实际货物不符，催促出发的人拒绝重新清点。", "查明了这次交接的差错", "委托人为何隐瞒差错"),
            "opening_chance": ("附带的条件", "一件能解决眼前困难的工具被送到你手里，却附着尚未签收的责任单。", "确认了工具的使用条件", "这项责任最终要交给谁"),
            "opening_debt": ("期限之前", "债务凭据提前到期，对方提出以一次陌生任务抵偿。", "谈下了新的履约办法", "这份委托为何只找你"),
            "opening_mystery": ("对不上的记录", "一份日常记录与现场痕迹对不上，登记人却说只是你记错了。", "证实异常并非记忆错误", "谁有权限改动记录"),
            "opening_escape": ("封锁前一刻", "出口正在逐一封闭，核查者已经知道你的目的地。", "离开了第一道封锁", "是谁泄露了行程"),
            "opening_homecoming": ("熟悉的门", "你认得这里的每条路，旧相识却劝你不要再按旧规矩敲门。", "重新接上了一条旧关系", "人们为何不愿提起最近的变化"),
            "opening_disruption": ("今天的新规", "新的限制突然公布，昨天答应别人的事今天已无法照常完成。", "找到暂时兑现承诺的办法", "新规定为何急着生效"),
            "opening_rescue": ("求助之后", "一个需要帮助的人来到门前，却请求你不要通知正在找他的人。", "完成了眼前的援助并问清意愿", "求助者为何不肯回到原来的队伍"),
        }
        title, incident, success, question = profiles.get(pattern, profiles["opening_survival"])
        goal = effects.get("present_crisis", {}).get("goal") or effects.get("opening_pattern", {}).get("goal", "解决眼前的困境")
        crisis = chosen("present_crisis")
        if crisis:
            success = {"crisis_quota": "争取到重新核查扣押物资的机会", "crisis_missing": "确定失踪者离开的方向", "crisis_failure": "获得临时修复设施的条件"}.get(crisis, success)
        memories = {
            "hero_failed_rescue": "上次仓促行动留下的后果还在。你这次尤其留意能否接应同伴。",
            "hero_lone_survivor": "独自谋生让你习惯先看清交换条件，求助的话到了嘴边又停住。",
            "hero_sheltered": "离开熟悉的庇护后，你第一次需要自己判断这些话是否可信。",
        }
        companion = {
            "companion_old_friend": "旧友看出你的犹豫，没有替你做决定。",
            "companion_partner": "暂时的合作伙伴提醒你，别忘了双方原来的约定。",
            "companion_creditor": "曾受你帮助的人主动留下，但不愿再被你安排到安全的后方。",
        }.get(chosen("companion_history"), "附近有人也被这场变故绊住了脚步。")
        companion += effects.get('companion_boundary', {}).get('scene', '')
        pressure = {
            "opponent_procedure": "负责人把书面程序摆在面前，不肯给没有凭证的人开例外。",
            "opponent_trade": "负责人把人叫到一边，分别开出不同的交换条件。",
            "opponent_force": "负责人先封住通道，再让所有人在期限前答复。",
        }.get(chosen("opponent_temperament"), "负责通行的人要求你先证明有资格继续介入。")
        if state.revision == 0:
            text = f"你来到{place}，眼下要做的是{goal}。{incident}{memories.get(chosen('hero_history'), '')}{companion}"
            choices = [("help", "先帮同行者解决眼前困难", "消耗 1 补给，换来具体协助"), ("clue", "核对现场痕迹与记录", "掌握线索，但独自承担调查"), ("supply", "先收集可用的备用物资", "增加 2 补给，调查会延后")]
            if pattern in ("opening_mystery", "opening_awakening", "opening_homecoming"):
                choices = choices[:2]
            elif pattern == "opening_survival":
                choices = [choices[0], choices[2]]
        elif state.revision == 1:
            title = "行动的条件"
            text = f"要继续{goal}，你还需要进入{place}的内侧。{pressure}"
            if state.ally:
                text += "你刚刚帮助的人愿意替你分担一段工作。"
            if state.clue:
                text += "你保留下的记录让对方无法再把事情推成一句误会。"
            if state.history[-1]["choice_id"] == "supply":
                text += "收集物资耽误了时间，留给你的通行窗口更短了。"
            choices = [("wait", "从外围等待一次通行机会", "保留物资，但错过从容处理的时间")]
            if state.ally:
                choices.insert(0, ("ally", "请同行者协助分担任务", "已有帮助换来接应"))
            if state.clue:
                choices.insert(0, ("proof", "用现场记录要求重新核对", "保留证据，留下调查痕迹"))
            if state.supplies >= 2:
                choices.append(("pay", "付出两份物资换取协助", "消耗 2 补给，不凭空获得盟友"))
        elif state.revision == 2:
            title = "带着什么离开"
            text = f"你已经获得继续介入的机会，但还不能说{goal}已经完成。" + ("等待耗掉了余裕，你必须先决定保住什么。" if state.history[-1]["choice_id"] == "wait" else "眼前出现了可以推进一步的缺口，但做出决定就要承担后果。")
            choices = [("leave", "暂时撤出，保留已经得到的收获", "目标尚未完成，留下下一次行动的理由")]
            if state.ally or state.clue:
                choices.insert(0, ("expose", "用已有帮助或证据推进当前目标", "推进一层，不一次揭晓全部真相"))
            if state.supplies >= 1:
                choices.append(("rescue", "付出一份物资，换取持续接应", "消耗 1 补给，推进目标并承担后续责任"))
        else:
            title, text, choices = "本段旅程结束", state.history[-1]["result"], []
            choices = [("continue_recover", "先补给并兑现一部分承诺，再继续", "补给 +1，欠下一份交换责任"), ("settle", "以当前收获结束这段故事", "保留未解问题，不再追加事件")]
            if state.clue or state.ally:
                choices.insert(0, ("continue_trace", "沿已有线索或同行者指引继续", "保留当前资源，进入后续事件"))
        suggestions = {"hero_cautious": ("clue", "wait", "leave"), "hero_bargainer": ("supply", "pay", "rescue"), "hero_impulsive": ("help", "ally", "expose")}.get(chosen("hero_temperament"), ())
        warnings = unparsed_warnings(blueprint)
        return {"state": state.model_dump(), "title": title, "text": text, "completed": state.revision == 3,
                "goal": goal, "success": success, "next_question": question, "warnings": warnings,
                "choices": [{"id": key, "label": label, "cost": cost, "suggested": key in suggestions} for key, label, cost in choices]}

    def choose_design(self, state, scene, choice):
        key = choice["id"]
        if key in FOLLOWUP_DELTAS:
            return self.choose_followup(state, scene, choice)
        results = {
            "help": "你用一份物资解决了对方眼前的困难，换来一次具体的协助。对方愿意同行，但这还不是无条件的信任。",
            "clue": "你比对了独立记录，保住一条能继续核实的线索。它还不能解释全部经过。",
            "supply": "你多收起两份可用物资，代价是调查被推迟。通行窗口正在缩短。",
            "ally": "同行者接下分担的工作，你得以继续接近目标。这次合作留下了一份要兑现的承诺。",
            "proof": "对方重新核对了你提交的记录，允许你继续介入，也记下了这次调查。",
            "pay": "两份物资换来一次协助。你拿到了行动条件，自己的储备也随之减少。",
            "wait": "你终于等到一段空当，但已经没有足够时间从容处理所有问题。",
            "leave": f"你暂时离开，保住了已有的收获。{scene['goal']}仍未完成，下一次行动需要补上眼下缺少的条件。",
            "expose": f"靠已经争取到的帮助或证据，你{scene['success']}。事情向前推进了一步，但{scene['next_question']}，仍需要继续查明。",
            "rescue": f"你交出一份物资换来持续接应，{scene['success']}。储备减少了，这段合作也带来了必须兑现的新责任。",
        }
        state.supplies += {"help": -1, "supply": 2, "pay": -2, "rescue": -1}.get(key, 0)
        state.ally = state.ally or key in ("help", "rescue")
        state.clue = state.clue or key == "clue"
        state.history.append({"scene": scene["title"], "context": scene["text"], "cost": choice["cost"], "choice_id": key, "choice": choice["label"], "result": results[key]})
        state.revision += 1
        self._save(state)
        return self.view(state)

    def followup_scene(self, state, blueprint):
        if state.arc_finished:
            return {"state": state.model_dump(), "title": "篇章已收束", "text": state.history[-1]["result"], "completed": True, "choices": [], "warnings": unparsed_warnings(blueprint)}
        effects = blueprint.design_effects
        companion_goal = effects.get('companion_motive', {}).get('goal', '兑现原来的承诺')
        opponent_goal = effects.get('opponent_motive', {}).get('goal', '维持眼前的资源分配')
        if state.revision == 4:
            title = "先兑现谁的承诺"
            text = (f"同行者还记得你们的约定。对方也需要{companion_goal}，不能永远替你让路。" if state.ally else "你还没有可靠的同行者。一个愿意提供消息的人提出，你必须先帮忙整理被延误的交接物资。")
            text += f"你带着上一段留下的 {state.supplies} 份物资来到交接处，欠下的交换责任还有 {state.debt} 份。"
            if state.ally:
                text += effects.get('companion_boundary', {}).get('scene', '')
            choices = [("negotiate_time", "把双方目标排进同一份时间表", "建立合作，但新增一份承诺"), ("go_alone", "拒绝继续交换，独自调查", "不添债务，关系疏远")]
            if state.supplies > 0:
                choices.insert(0, ("honor_partner", "先用一份物资兑现约定", "补给 -1，信任增加，偿还一份责任"))
        elif state.revision == 5:
            title = "对方也在行动"
            text = f"负责人想要{opponent_goal}。你们停下处理承诺时，对方也收走了公开的交接记录，只留下空白的公示栏。"
            text += "关系缓和后，同行者提醒你：交接人手里通常还有一份回执。" if state.trust > 0 else "没人主动替你说话。你只能自己寻找仍愿意作证的人。"
            choices = [("seek_receipt", "去找实际交接人核对回执", "获得可核验来源，也让调查变得公开"), ("accept_private", "接受私下通融，不再追查记录", "眼前可通行，但真相暂时无法验证")]
        elif state.revision == 6:
            title = "两份记录之间"
            if 'receipt' in state.facts:
                text = "交接人拿出了自己的回执。日期与公示一致，数量却不同。回执上有两枚印记，第二枚盖在改动之后；这说明发生过重新调拨，还不能说明是谁授意。"
                choices = [("verify_order", "到留档处核对第二枚印记与原件", "验证当前疑点，不猜测更高层身份"), ("keep_receipt", "保留回执，暂不公开质疑", "留存线索，延后揭露")]
            else:
                text = "你得到了私下通行的机会，却没有拿到回执。眼前的顺利不等于已经知道事情的来由。"
                choices = [("record_limits", "记下已知范围，不把猜测当成事实", "保留通行条件，承认谜题未解")]
        else:
            title = "选择如何收束"
            text = "眼前已经不需要再往前赶。你必须决定这次行动要留下什么结果，而不是把所有问题都拖到下一次。"
            choices = [("end_depart", "带着已知收获离开", "保留未决事项，结束本篇")]
            if 'diversion_verified' in state.facts:
                choices.insert(0, ("end_public", "公开核实过的调拨证据", "改变局部规则，也承担公开立场的代价"))
            if state.trust > 0:
                choices.append(("end_cooperate", "与同行者先建立长期互助", "关系成为收获，不承诺谜题已经全解"))
        return {"state": state.model_dump(), "title": title, "text": text, "completed": False, "warnings": unparsed_warnings(blueprint),
                "choices": [{"id": key, "label": label, "cost": cost} for key, label, cost in choices]}

    def choose_followup(self, state, scene, choice):
        key = choice['id']
        results = {
            'continue_trace': '你没有重新开始。已有的消息和协助把你带到下一处交接点，物资仍是离开时的那些。',
            'continue_recover': '你用一次之后必须完成的帮工换来一份补给。喘息并非免费，但现在有余力继续了。',
            'settle': '你决定以当前收获结束这一段。尚未核实的疑问留在记录里，没有被当作答案。',
            'honor_partner': '一份物资交到对方手里，原来的一项约定得到兑现。对方终于愿意把自己的安排告诉你。',
            'negotiate_time': '你们把彼此的事排进同一份安排，愿意合作，也承认还有一项责任没有完成。',
            'go_alone': '你拒绝继续交换。对方收回了额外的帮助，你没有多欠一份责任，但关系比之前远了。',
            'seek_receipt': '交接人愿意出示自己保存的回执。你先记下日期与经手人，没有立刻指认谁在说谎。',
            'accept_private': '你接受了眼前的通融，也放弃这次核对回执的机会。便利不能被写成真相。',
            'verify_order': '留档原件与第二枚印记相符：眼前这批物资曾被负责人改拨给另一处急需点，却没有同步公开记录。数量矛盾有了可核验的解释；这不证明更早的所有异常都出自同一人。',
            'keep_receipt': '你留下回执，但没有看到留档原件。重新调拨仍是待验证的解释。',
            'record_limits': '你记下自己没有拿到回执，也没有核对原件。下一步若要追查，需要补上证据，而不是重复猜测。',
            'end_public': '你公开了回执与原件的对应部分，促成这次调拨补记和受影响者复核。负责人必须解释自己的决定，你也从此需要对公开的证据负责。',
            'end_cooperate': '你与同行者约定了下一次互助的边界。最重要的收获是这段经得起分歧的关系；未解的问题仍未解。',
            'end_depart': '你带着已经得到的帮助、消息和剩余物资离开。此处的经历告一段落，没有凭空多出新的敌人逼你继续。',
        }
        state.supplies += FOLLOWUP_DELTAS[key]
        state.history.append({'scene': scene['title'], 'context': scene['text'], 'cost': choice['cost'], 'choice_id': key, 'choice': choice['label'], 'result': results[key]})
        state.revision += 1
        updates = followup_state([entry['choice_id'] for entry in state.history])
        for name, value in updates.items():
            setattr(state, name, value)
        self._save(state)
        return self.view(state)


FOLLOWUP_DELTAS = {key: 0 for key in ('continue_trace', 'settle', 'negotiate_time', 'go_alone', 'seek_receipt', 'accept_private', 'verify_order', 'keep_receipt', 'record_limits', 'end_public', 'end_cooperate', 'end_depart')}
FOLLOWUP_DELTAS.update({'continue_recover': 1, 'honor_partner': -1})


def followup_state(actions):
    trust, debt, facts = 0, 0, []
    for action in actions:
        if action in ('continue_recover', 'negotiate_time'):
            debt += 1
        if action in ('honor_partner', 'negotiate_time'):
            trust += 1
        if action == 'honor_partner':
            debt = max(0, debt - 1)
        if action == 'go_alone':
            trust -= 1
        if action == 'seek_receipt':
            facts.append('receipt')
        if action == 'verify_order':
            facts.append('diversion_verified')
    return {'trust': trust, 'debt': debt, 'facts': facts,
            'arc_finished': any(action in ('settle', 'end_public', 'end_cooperate', 'end_depart') for action in actions)}
