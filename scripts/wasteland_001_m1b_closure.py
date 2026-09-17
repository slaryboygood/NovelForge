"""M1B — Semantic Reconciliation Final Closure（真实 LLM verifier，shadow only）。

流程：M1B baseline → deterministic IR（570）→ 真实 LLM verifier（570/570，批量严格 JSON）
→ Golden V3（expected / actual / difference）→ Repair Queue V3 → 最终报告。

硬边界：不改 legacy 内容 / authoritative V5 / StoryState / Canon，不 freeze。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pydantic import Field, ValidationError  # noqa: E402

from novelforge.models import StrictModel  # noqa: E402
from novelforge.story_engine.chapter_ir.compiler import ChapterFieldCompiler  # noqa: E402
from novelforge.story_engine.chapter_ir.extractor import (  # noqa: E402
    LegacyIRSemanticExtractor,
)
from novelforge.story_engine.chapter_ir.migration import LegacyChapterMigration  # noqa: E402
from novelforge.story_engine.chapter_ir.state import (  # noqa: E402
    DEFAULT_TRANSITION_BINDINGS,
    build_default_registry,
)
from novelforge.story_engine.chapter_ir.verifier import (  # noqa: E402
    AUTHORITATIVE_BINDING_CONFLICT,
    DECISION_WRONG_ACTOR,
    DOG_MENTION_AS_ACTION,
    DOG_WRONG_ACTOR,
    DeterministicSemanticVerifier,
    categorize,
)

EXPORTS = ROOT / "workspace" / "wasteland_001_exports"
RECON_DIR = EXPORTS / "chapter_ir_v1" / "reconciliation"
OUT_DIR = EXPORTS / "chapter_ir_v1" / "m1b"
CANDIDATE = EXPORTS / "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5.json"
STATE_FILE = (ROOT / "novel" / "authoring" / "story_engine" / "state"
              / "runtime_wasteland_001" / "v000001.json")
CANON_DB = ROOT / "novel" / "authoring" / "story_engine" / "canon" / "wasteland_001.sqlite"
FIXTURES = ROOT / "tests" / "fixtures" / "chapter_ir_pilot"
ENV_FILE = ROOT / ".env.local"
MODEL = "deepseek-chat"
BATCH = 8

ALIASES = {
    "韩彻": "ENTITY_PROTAGONIST", "阿灰": "ENTITY_DOG_AHUI", "老鸦": "ENTITY_RAVEN",
    "秦霜": "ENTITY_QINSHUANG", "穆医生": "ENTITY_DOCTOR_MU", "织工": "ENTITY_WEAVER",
    "锈牙": "ENTITY_FACTION_RUST_TOOTH", "黑塔": "ENTITY_FACTION_BLACK_TOWER",
    "缝合会": "ENTITY_FACTION_STITCHING", "盐路": "ENTITY_FACTION_SALT_ROAD",
    "编号犬": "ENTITY_HUNTER_DOG_01", "荒原犬": "ENTITY_HUNTER_DOG_01",
    "猎团": "ENTITY_FACTION_HUNTERS", "笼中同类": "ENTITY_CAGED_KIN",
}
KIND_INDEX = {"dog": ["ENTITY_DOG_AHUI", "ENTITY_HUNTER_DOG_01", "ENTITY_CAGED_KIN"]}
ACTOR_NAMES = {
    "ENTITY_PROTAGONIST": "韩彻", "ENTITY_DOG_AHUI": "阿灰", "ENTITY_RAVEN": "老鸦",
    "ENTITY_QINSHUANG": "秦霜", "ENTITY_DOCTOR_MU": "穆医生", "ENTITY_WEAVER": "织工",
    "ENTITY_FACTION_BLACK_TOWER": "黑塔", "ENTITY_FACTION_STITCHING": "缝合会",
    "ENTITY_FACTION_SALT_ROAD": "盐路商队", "ENTITY_FACTION_RUST_TOOTH": "锈牙",
    "ENTITY_FACTION_HUNTERS": "猎团", "ENTITY_HUNTER_DOG_01": "编号荒原犬",
    "ENTITY_CAGED_KIN": "笼中同类", "ENTITY_THREE_FACTIONS": "三方代表",
    "ENTITY_RUST_SETTLEMENT": "铁锈集", "ENTITY_SETTLEMENT_EDGE": "边缘聚落",
    "ENTITY_EXTERNAL_TEAM": "外部队伍",
}


# ---------------------------------------------------------------- LLM verifier schema
class LLMDecision(StrictModel):
    exists: bool = False
    owner_id: str = ""
    action_type: str = ""
    evidence: str = ""
    valid: bool = False


class LLMTurn(StrictModel):
    exists: bool = False
    type: str = ""
    evidence: str = ""
    valid: bool = False


class LLMPayoff(StrictModel):
    exists: bool = False
    type: str = ""
    evidence: str = ""
    valid: bool = False


class LLMDog(StrictModel):
    presence: bool = False
    role: str = "absent"
    actor_evidence: str = ""
    valid: bool = True


class LLMPrimaryTransition(StrictModel):
    exists: bool = False
    state_key: str = ""
    from_state: str = ""
    to_state: str = ""
    assertion_mode: str = ""
    narrative_role: str = ""
    valid: bool = True


class LLMVerificationResult(StrictModel):
    chapter_uuid: str = Field(min_length=3, max_length=128)
    event_actor_checks: dict[str, str] = Field(default_factory=dict)
    decision: LLMDecision = Field(default_factory=LLMDecision)
    turn: LLMTurn = Field(default_factory=LLMTurn)
    payoff: LLMPayoff = Field(default_factory=LLMPayoff)
    dog: LLMDog = Field(default_factory=LLMDog)
    primary_transition: LLMPrimaryTransition = Field(default_factory=LLMPrimaryTransition)
    future_or_historical_refs: list[str] = Field(default_factory=list)
    legacy_field_conflicts: list[str] = Field(default_factory=list)
    verdict: Literal["AGREE", "DISAGREE", "AMBIGUOUS"] = "AMBIGUOUS"
    confidence: float = Field(default=0.6, ge=0, le=1)


# ---------------------------------------------------------------- helpers
def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _digest_payload(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     default=str).encode("utf-8")).hexdigest()[:16]


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    env.update({key: value for key, value in os.environ.items()
                if key in ("DEEPSEEK_API_KEY", "ARK_API_KEY")})
    return env


class LLMVerifierClient:
    def __init__(self, env: dict[str, str]) -> None:
        key = env.get("DEEPSEEK_API_KEY", "")
        if not key:
            raise RuntimeError("BLOCKED_REAL_LLM_VERIFIER_UNAVAILABLE: 缺少 DEEPSEEK_API_KEY")
        self.key = key
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.key}"})
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
        self.calls += 1
        usage = body.get("usage") or {}
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        return body

    def verify_batch(self, chapters: list[dict[str, Any]],
                     bindings: list[dict[str, Any]]) -> list[LLMVerificationResult]:
        prompt = build_prompt(chapters, bindings)
        last_error = ""
        for attempt in range(2):
            body = self._chat({
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt if attempt == 0 else
                     prompt + "\n\n上一次输出不是合法 JSON，请只输出合法 JSON 对象。"}],
                "temperature": 0, "max_tokens": 4000,
                "response_format": {"type": "json_object"}})
            content = body["choices"][0]["message"]["content"]
            try:
                payload = json.loads(content)
                rows = payload["chapters"]
                return [LLMVerificationResult.model_validate(row, strict=True) for row in rows]
            except (json.JSONDecodeError, KeyError, ValidationError) as exc:
                last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
                time.sleep(1)
        raise RuntimeError(f"LLM_VERIFIER_PARSE_FAILED: {last_error}")


SYSTEM_PROMPT = (
    "你是小说章节语义校验器，只做结构判断，不改写内容、不给修文建议、不创造剧情。"
    "输入是某一章的 legacy 字段、concrete_events、deterministic IR 摘要、允许的实体 id 与"
    "合法 Typed State 迁移绑定。你要判断 deterministic IR 的语义是否正确。"
    "严格规则：decision 必须由 focal owner（默认 ENTITY_PROTAGONIST）真正做出选择，"
    "NPC 发言 / 发现线索 / 环境事实 / 狗的反应都不能算主角 decision；"
    "dog 的 supportive/involved/independent 必须有 evidence event 的 actor 真正是 "
    "ENTITY_DOG_AHUI（只是被提到、被讨论、被困、被救、被交易都不算）；"
    "payoff 必须回答本章目标经过冲突后实际得到的回报，不能等于 trigger 或 hook；"
    "turn 不能来自普通损失；primary transition 只能取 binding 表中该章对应的迁移，"
    "其他章节引用同一状态必须标成 historical/future/observation。"
    "输出严格 JSON 对象：{\"chapters\":[{\"chapter_uuid\":\"...\",\"event_actor_checks\":{}," 
    "\"decision\":{\"exists\":false,\"owner_id\":\"\",\"action_type\":\"\",\"evidence\":\"\","
    "\"valid\":false},\"turn\":{\"exists\":false,\"type\":\"\",\"evidence\":\"\",\"valid\":false},"
    "\"payoff\":{\"exists\":false,\"type\":\"\",\"evidence\":\"\",\"valid\":false},"
    "\"dog\":{\"presence\":false,\"role\":\"absent\",\"actor_evidence\":\"\",\"valid\":true},"
    "\"primary_transition\":{\"exists\":false,\"state_key\":\"\",\"from_state\":\"\","
    "\"to_state\":\"\",\"assertion_mode\":\"\",\"narrative_role\":\"\",\"valid\":true},"
    "\"future_or_historical_refs\":[],\"legacy_field_conflicts\":[],"
    "\"verdict\":\"AGREE|DISAGREE|AMBIGUOUS\",\"confidence\":0.0}]}，"
    "只输出 JSON，不要解释。")


def build_prompt(chapters: list[dict[str, Any]],
                 bindings: list[dict[str, Any]]) -> str:
    lines = ["合法 Typed State 绑定（state_key, to_state, 章节号）：",
             json.dumps(bindings, ensure_ascii=False), "",
             "允许的实体 id：", json.dumps(ACTOR_NAMES, ensure_ascii=False), "",
             f"请校验以下 {len(chapters)} 章："]
    for row in chapters:
        lines.append(json.dumps(row, ensure_ascii=False))
    return "\n".join(lines)


def chapter_input(ir, chapter: dict[str, Any], verification) -> dict[str, Any]:
    return {
        "chapter_uuid": ir.chapter_uuid,
        "display_number": ir.temporal_position,
        "goal": chapter.get("goal"), "start_state": chapter.get("start_state"),
        "trigger": chapter.get("trigger"),
        "protagonist_action": chapter.get("protagonist_action"),
        "opposition": chapter.get("opposition"), "escalation": chapter.get("escalation"),
        "legacy_decision": chapter.get("decision") or chapter.get("choice"),
        "cost": chapter.get("cost"), "turn": chapter.get("turn"),
        "payoff": chapter.get("payoff"), "loss": chapter.get("loss"),
        "end_state": chapter.get("end_state"),
        "information_release": chapter.get("information_release"),
        "world_state_change": chapter.get("world_state_change"),
        "concrete_events": chapter.get("events") or [],
        "deterministic_ir": {
            "primary_transition": ([next(item.state_key for item in ir.state_transitions
                                         if item.narrative_role == "primary"),
                                    next(item.to_state for item in ir.state_transitions
                                         if item.narrative_role == "primary")]
                                   if any(item.narrative_role == "primary"
                                          for item in ir.state_transitions) else None),
            "dog": {"presence": ir.dog.physical_presence, "role": ir.dog.role},
            "decision_owner": verification.decision.actor_id,
            "issues": verification.issues,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 章（冒烟）")
    parser.add_argument("--resume", action="store_true", help="复用已有结果，只补缺失章节")
    parser.add_argument("--batch", type=int, default=BATCH)
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not CANDIDATE.is_file():
        print("BLOCKED: candidate 不存在")
        return 2
    payload = json.loads(CANDIDATE.read_text(encoding="utf-8-sig"))
    chapters = payload["chapters"]
    if args.limit:
        chapters = chapters[:args.limit]
    baseline = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_digest": _digest(CANDIDATE),
        "story_state_digest": _digest_payload(
            json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))),
        "canon_digest": _digest(CANON_DB) if CANON_DB.is_file() else "",
        "chapters": len(payload["chapters"]),
        "reconciliation_report_exists": (RECON_DIR
                                         / "WASTELAND_001_CHAPTER_IR_RECONCILIATION_REPORT.md").is_file(),
    }
    (OUT_DIR / "M1B_BASELINE.json").write_text(
        json.dumps(baseline, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    env = _load_env()
    try:
        client = LLMVerifierClient(env)
    except RuntimeError as exc:
        (OUT_DIR / "M1B_BLOCKED.json").write_text(json.dumps(
            {"status": "BLOCKED_REAL_LLM_VERIFIER_UNAVAILABLE", "detail": str(exc)},
            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("BLOCKED_REAL_LLM_VERIFIER_UNAVAILABLE:", exc)
        return 3
    registry = build_default_registry({b.state_key: b.display_number
                                       for b in DEFAULT_TRANSITION_BINDINGS})
    extractor = LegacyIRSemanticExtractor(
        novel_id="wasteland_001", dog_entity_id="ENTITY_DOG_AHUI",
        protagonist_id="ENTITY_PROTAGONIST", entity_aliases=ALIASES, kind_index=KIND_INDEX)
    deterministic_verifier = DeterministicSemanticVerifier()
    llm_proposals = json.loads((FIXTURES / "LLM_PROPOSALS.json")
                               .read_text(encoding="utf-8"))["chapters"]
    inputs: list[dict[str, Any]] = []
    irs: dict[str, Any] = {}
    det_results: dict[str, Any] = {}
    for chapter in chapters:
        ir = extractor.to_ir(extractor.extract(chapter, backend="deterministic"), chapter)
        legacy_id = str(chapter["id"])
        if legacy_id in llm_proposals:
            try:
                llm_extractor = LegacyIRSemanticExtractor(
                    novel_id="wasteland_001", dog_entity_id="ENTITY_DOG_AHUI",
                    protagonist_id="ENTITY_PROTAGONIST", entity_aliases=ALIASES,
                    kind_index=KIND_INDEX,
                    llm_provider=lambda _c, _p=dict(llm_proposals[legacy_id]): _p)
                candidate_ir = llm_extractor.to_ir(
                    llm_extractor.extract(chapter, backend="llm"), chapter)
                det_dog = (ir.dog.role, ir.dog.physical_presence)
                llm_dog = (candidate_ir.dog.role, candidate_ir.dog.presence
                           if hasattr(candidate_ir.dog, "presence")
                           else candidate_ir.dog.physical_presence)
                det_primary = next((item.to_state for item in ir.state_transitions
                                    if item.narrative_role == "primary"), "")
                llm_primary = next((item.to_state for item in candidate_ir.state_transitions
                                    if item.narrative_role == "primary"), "")
                if det_dog != llm_dog or det_primary != llm_primary:
                    ir = candidate_ir
            except Exception:  # noqa: BLE001 - proposal 不合法则保留 deterministic
                pass
        verification = deterministic_verifier.verify(ir, chapter, registry)
        irs[ir.chapter_uuid] = ir
        det_results[ir.chapter_uuid] = verification
        inputs.append(chapter_input(ir, chapter, verification))
    bindings = [{"state_key": b.state_key, "to_state": b.to_state,
                 "chapter": b.display_number} for b in DEFAULT_TRANSITION_BINDINGS]
    llm_results: dict[str, LLMVerificationResult] = {}
    failures: list[dict[str, Any]] = []
    existing_path = OUT_DIR / "WASTELAND_001_LLM_VERIFICATION.json"
    if args.resume and existing_path.is_file():
        existing = json.loads(existing_path.read_text(encoding="utf-8"))
        for row in existing.get("rows", []):
            if row.get("llm"):
                llm_results[row["chapter_uuid"]] = LLMVerificationResult.model_validate(
                    row["llm"], strict=True)
        print(f"  resume: 已有 {len(llm_results)} 章结果", flush=True)
    pending = [row for row in inputs if row["chapter_uuid"] not in llm_results]
    batch_size = max(2, int(args.batch))
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        try:
            rows = client.verify_batch(batch, bindings)
        except Exception as exc:  # noqa: BLE001
            failures.append({"start": start, "error": str(exc)[:200]})
            continue
        for row in rows:
            llm_results[row.chapter_uuid] = row
        print(f"  verified {len(llm_results)}/{len(inputs)} (calls={client.calls})", flush=True)
    stats = {
        "llm_verifier_invoked": len(llm_results),
        "llm_verifier_agree": sum(1 for row in llm_results.values() if row.verdict == "AGREE"),
        "llm_verifier_disagree": sum(1 for row in llm_results.values()
                                     if row.verdict == "DISAGREE"),
        "llm_verifier_ambiguous": sum(1 for row in llm_results.values()
                                      if row.verdict == "AMBIGUOUS"),
        "llm_calls": client.calls, "prompt_tokens": client.prompt_tokens,
        "completion_tokens": client.completion_tokens,
        "batch_failures": len(failures),
    }
    rows_out = []
    for value in inputs:
        uuid = value["chapter_uuid"]
        ir = irs[uuid]
        det = det_results[uuid]
        llm = llm_results.get(uuid)
        rows_out.append({"chapter_uuid": uuid, "display_number": value["display_number"],
                         "deterministic": det.model_dump(mode="json"),
                         "llm": llm.model_dump(mode="json") if llm else None,
                         "dog": {"role": ir.dog.role,
                                 "presence": ir.dog.physical_presence,
                                 "evidence": ir.dog.evidence_event_ids},
                         "primary_transition": next(
                             ({"state_key": item.state_key, "from_state": item.from_state,
                               "to_state": item.to_state, "assertion_mode": item.assertion_mode,
                               "narrative_role": item.narrative_role}
                              for item in ir.state_transitions
                              if item.narrative_role == "primary"), None)})
    (OUT_DIR / "WASTELAND_001_LLM_VERIFICATION.json").write_text(
        json.dumps({"stats": stats, "failures": failures, "rows": rows_out},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("[M1B] stats:", json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
