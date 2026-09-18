"""让 tests/acceptance 下的测试能 import acceptance_support。"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for candidate in (HERE, ROOT / "tests" / "v4" / "isolation",
                  ROOT / "tests" / "agent"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
