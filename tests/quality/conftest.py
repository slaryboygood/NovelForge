"""让 tests/quality 下的所有测试（含 repair/ 子目录）都能 import quality_support。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
