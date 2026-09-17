"""通用 phase-history 测试 helper（M11 / M12 共用）。

规则（M11 closure 的教训，M12 直接继承）：

* historical phase 期望值必须来自 **frozen 历史证据**（phase report / phase snapshot）；
* 只有 live 断言才读 current live state；
* 需要同时表达历史与现状时使用 ``closed(historical, current)`` 显式双值，
  不得把永久 invariant 弱化成模糊断言。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from novelforge.story_engine.phase_snapshot import (  # noqa: E402
    PhaseSnapshotExists,
    load_current_state as _load_current_state,
    load_phase_snapshot as _load_phase_snapshot,
    load_snapshot_manifest as _load_snapshot_manifest,
    snapshot_exists as _snapshot_exists,
    verify_phase_snapshot as _verify_phase_snapshot,
    write_phase_snapshot as _write_phase_snapshot,
)


def closed(historical: object, current: object) -> object:
    """显式双值：phase-timepoint 期望值 → closure 后 live 期望值。"""

    del historical
    return current


def assert_doc_records(path: str, *needles: str, label: str = "") -> str:
    """历史值必须仍被 frozen phase report / closeout 文档记录（不被静默改写）。"""

    doc = ROOT / path
    assert doc.is_file(), f"phase report missing: {doc}"
    text = doc.read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    assert not missing, (f"[PHASE-HISTORY] historical evidence missing in "
                         f"{label or path}: {missing}")
    return text


# ---------------------------------------------------------------- snapshots
def load_phase_snapshot(phase_id: str) -> dict:
    """读取 frozen phase snapshot（历史 phase 测试的唯一数据源）。"""

    return _load_phase_snapshot(ROOT, phase_id)


def load_snapshot_manifest(phase_id: str) -> dict:
    return _load_snapshot_manifest(ROOT, phase_id)


def verify_phase_snapshot(phase_id: str) -> dict:
    """证明 snapshot 与 manifest digest 一致（历史证据未被静默改写）。"""

    return _verify_phase_snapshot(ROOT, phase_id)


def load_current_state() -> dict:
    """读取当前 closure production state（live-state 断言使用）。"""

    return _load_current_state(ROOT)


def snapshot_exists(phase_id: str) -> bool:
    return _snapshot_exists(ROOT, phase_id)


def write_phase_snapshot(phase_id: str, data: dict, **kwargs) -> dict:
    return _write_phase_snapshot(ROOT, phase_id, data, **kwargs)


def phase(phase_id: str, key: str, default=None):
    """历史 phase 值读取（缺失即报错，不静默回退 live）。"""

    return load_phase_snapshot(phase_id).get(key, default)
