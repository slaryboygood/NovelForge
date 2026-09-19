"""Dogfood-only deterministic stub server (NovelForge V4.0.1 skill dogfood).

Reuses the composition in ``scripts/studio_ui_test_server.py`` (isolated data
root + stub gateway + fixture plugin, zero real model calls) and extends the
deterministic generation script with the two generation tasks that the
official browser-gate fixture does not cover: ``theme`` and ``character_arc``.

Why this file exists
--------------------
``create-new-story-blueprint`` asks for premise -> theme -> world -> character
-> character_arc -> story_arc -> structural_unit -> chapter -> scene. The
official fixture script only provides premise / world / character / story_arc /
structural_unit / chapter / scene payloads, so ``theme`` and ``character_arc``
return 422 ``GENERATION_UNAVAILABLE`` (structured output failed schema
validation) before any real operation could be observed.

This is a **test fixture**, not product code: it is used only by the V4.0.1
skill dogfood branch and never touches ``src/`` / ``ui/`` / ``novel/``.

Usage::

    .venv\\Scripts\\python.exe tests/v4/skills/dogfood_401_stub_server.py \
        --port 8041 --root <isolated root>
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
OFFICIAL_STUB = REPO / "scripts" / "studio_ui_test_server.py"


def _load_official_stub() -> Any:
    spec = importlib.util.spec_from_file_location("nf_dogfood_official_stub", OFFICIAL_STUB)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["nf_dogfood_official_stub"] = module
    spec.loader.exec_module(module)
    return module


def _theme_payload() -> dict[str, Any]:
    return {
        "theme": "为了活下去而牺牲他人，是否仍然是活下去",
        "statement": "任何以他人生命为代价的生存方案都必须被公开承担",
        "counter_theme": "共同体可以为了整体牺牲少数人",
        "motifs": ["断电", "水位刻度", "未签名的许可"],
    }


def _character_arc_payload() -> dict[str, Any]:
    return {
        # The contract (CharacterArcPayload) requires character_id (min_length=1)
        # even though the engine overwrites it with the real parent id. Omitting
        # it makes the deterministic stub fail schema validation with 422
        # GENERATION_UNAVAILABLE, which is what the V4.0.1 dogfood hit.
        "character_id": "char_00_placeholder",
        "start_state": "只相信自己修得好设备",
        "internal_conflict": "想救人又不敢把决定权交出去",
        "external_pressure": "七十二小时倒计时与许可被撤回",
        "key_turns": [
            "发现破坏者是内部人",
            "备用电池组被盗后被迫求助水务委",
        ],
        "midpoint_change": "承认自己无法独自修复",
        "crisis": "必须在水与电之间做选择",
        "climax_choice": "把选择权交给全城",
        "end_state": "愿意让别人承担自己的决定",
    }


def _rewrite_variant(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a payload that differs only in the field dogfood rewrites.

    ``rewrite-node`` runs the model under operation ``rewrite.<node_type>`` and
    then rejects the whole write if any field outside ``target_fields`` changed.
    The official fixture has no entry for that operation at all, so the write
    failed schema validation before any real rewrite could be observed.
    """
    variant = dict(payload)
    for field in ("turn", "goal", "conflict", "outcome"):
        if isinstance(variant.get(field), str) and variant[field]:
            variant[field] = f"{variant[field]}（dogfood 改写）"
            break
    return variant


def main() -> int:
    module = _load_official_stub()
    official_script = module.generation_script
    official_seed = module.seed_clean_novel
    official_complete = module.StubProvider.complete

    def complete(self: Any, request: Any) -> Any:
        operation = str(getattr(request, "operation", ""))
        if operation not in self.script:
            print(f"[dogfood-stub] UNSCRIPTED operation={operation!r}", flush=True)
        return official_complete(self, request)

    module.StubProvider.complete = complete

    def generation_script() -> dict[str, Any]:
        script = official_script()
        script["theme"] = _theme_payload()
        script["character_arc"] = _character_arc_payload()
        for task, payload in list(script.items()):
            if isinstance(payload, dict):
                script[f"rewrite.{task}"] = _rewrite_variant(payload)
        return script

    def seed_clean_novel(root: Path, novel_id: str = "studio_clean") -> str:
        # The official seeder is not restart-idempotent: re-running the server
        # against an existing root raises PROFILE_EXISTS and kills the process.
        # During dogfood we restart often, so reuse an already-seeded novel.
        try:
            return official_seed(root, novel_id=novel_id)
        except Exception as exc:  # noqa: BLE001 - dogfood fixture, keep serving
            print(f"[dogfood-stub] reuse existing seeded novel {novel_id}: {exc}", flush=True)
            return novel_id if (root / "novel" / "authoring").exists() else ""

    module.generation_script = generation_script

    module.seed_clean_novel = seed_clean_novel
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())
