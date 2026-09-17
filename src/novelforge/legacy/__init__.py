"""Legacy Compatibility Boundary（V4-01）。

定位（`docs/v4/V4_MODULE_BOUNDARIES.md` §3.5）：

```text
Frozen V3 Module（原地保留）
        ↑
Legacy Adapter（本包；只读包装 + 明确的兼容清单）
        ↑
V4 Application Service
```

规则：

* frozen 模块在替换完成前**原地保留**，不为目录整齐搬运；
* 只有"仍需要兼容的能力"才登记进本包；
* 已删除的废弃数据（`novel/final/**`、570 章 historical）**不进入本包**；
* frozen 模块不得被新的业务写路径 import（守卫见 `tests/v4/isolation/`）。
"""

from .adapters import (
    LegacyAdapterError,
    describe_legacy_capabilities,
    legacy_adventure_status,
)
from .manifest import FROZEN_MODULES, FrozenModule, frozen_module, frozen_module_ids

__all__ = [
    "FROZEN_MODULES", "FrozenModule", "LegacyAdapterError",
    "describe_legacy_capabilities", "frozen_module", "frozen_module_ids",
    "legacy_adventure_status",
]

