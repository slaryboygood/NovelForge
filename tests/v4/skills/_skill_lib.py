"""共享 helper：加载 V4.0.1 Skill Library validator（唯一实现）。

测试只调用 `scripts/validate_v4_0_1_skills.py` 里的函数，避免在测试里复制一套校验规则。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load_validator():
    scripts = ROOT / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location(
        "novelforge_v4_0_1_skill_validator", scripts / "validate_v4_0_1_skills.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


__all__ = ["ROOT", "load_validator"]
