"""让 tests/plugins 下的测试能 import plugins_support，并让 fixture 模块可被 entry point 解析。

测试插件（`tests/plugins/fixtures/`）**不进入生产 discovery**（V4-09 §69）：
它们只通过显式 entry point / manifest path 在测试里被加载。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"

for candidate in (HERE, FIXTURES):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
