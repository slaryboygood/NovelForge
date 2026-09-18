"""Delivery 测试 fixture（零网络、零真实模型）。

复用 V4-04 / V4-05 / V4-06 的 Golden fixture（`tests/editor/editor_support.py`），
并额外建立"已接受 + 质量通过"的交付状态：

```text
generate/repair（V4-05 闭环）→ 全部节点 accept → 重新评估整本 Blueprint
```
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _load(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_editor_support = _load("editor_support_for_delivery",
                        ROOT / "tests" / "editor" / "editor_support.py")

editor_stack = _editor_support.editor_stack
repaired_scene_payload = _editor_support.repaired_scene_payload
repaired_chapter_payload = _editor_support.repaired_chapter_payload
scene_payload = _editor_support.scene_payload
current_payload = _editor_support.current_payload
NOVEL_ID = _editor_support.NOVEL_ID


def repair_script() -> list[Any]:
    return [repaired_chapter_payload(), repaired_scene_payload(sequence=1),
            repaired_scene_payload(sequence=2), repaired_scene_payload(sequence=3)]


def delivery_stack(tmp_path: Path, *, novel_id: str = NOVEL_ID,
                   clean: bool = True, repairable: bool = True,
                   script: Sequence[Any] | None = None
                   ) -> dict[str, Any]:
    """交付 fixture：clean=True 时先跑闭环修复 + accept + 重新评估。"""

    from novelforge.delivery import DeliveryService
    from novelforge.delivery.store import DeliveryStore

    stack = editor_stack(tmp_path, novel_id=novel_id, repairable=repairable,
                         script=list(script if script is not None else repair_script()))
    if clean:
        _make_clean_and_accepted(stack)
    stack["delivery_store"] = DeliveryStore(tmp_path, novel_id)
    stack["editor_store"] = stack["store"]
    stack["delivery"] = DeliveryService(
        tmp_path, novel_id, repository=stack["repository"],
        quality_store=stack["quality"].store, editor_store=stack["editor_store"],
        store=stack["delivery_store"], title="阿尔法计划")
    return stack


def _make_clean_and_accepted(stack: dict[str, Any]) -> None:
    review = stack["review"]
    repository = stack["repository"]
    quality = stack["quality"]
    # 1) V4-05 闭环：评估 → 修复 → 复核（让 Blueprint 通过质量门）
    loop = review.evaluate_and_repair()
    assert loop.status in ("passed", "repaired"), loop.reasons
    # 2) 全部节点 accept（作者确认；status 流转本身产生新 revision）
    for node in list(repository.all_nodes()):
        if str(node.status) == "accepted":
            continue
        repository.set_status(node.node_id, "accepted",
                              expected_revision=repository.current_revision(
                                  node.node_id))
    # 3) 对 accepted revision 重新评估一次（交付要求质量结论针对被选 revision）
    report = quality.evaluate()
    assert report.status == "passed", [row.code for row in report.issues]
    stack["clean_report"] = report
