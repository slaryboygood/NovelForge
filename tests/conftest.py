"""测试公共配置。

V4-01 Boundary Foundation（作者决策 A / B）：

* `novel/final/**`（69 个 tracked 正文文件）与 `workspace/wasteland_001_exports/**`
  （570 章 historical / M11 证据）被判定为废弃资产并删除；
* 依赖这些数据的历史里程碑验收（M11–M18 / wasteland / historical IR，共 52 个测试文件
  与 4 个 phase_history helper）同步删除 —— 它们验证的能力已经不存在；
* 因此不再需要 `historical_acceptance` marker 与自动标记 hook：
  默认套件 = 全部现存测试，历史套件为空（marker 保留给 V4 里程碑验收重新启用）。
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
