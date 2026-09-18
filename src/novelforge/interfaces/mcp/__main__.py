"""`python -m novelforge.interfaces.mcp` —— 以 stdio transport 启动 MCP Server。

环境变量：

```text
NOVELFORGE_PROJECT_ROOT  项目根目录（默认当前目录）
```

注意：不在 import 时扫描项目、打开作品或初始化模型（§41）。
"""

from __future__ import annotations

from .server import main

if __name__ == "__main__":  # pragma: no cover - 由 SDK stdio 会话驱动
    main()
