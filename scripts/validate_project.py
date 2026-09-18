"""验证当前故事构筑产品，不扫描历史小说生产数据。

post-release cleanup：V2/V3 Story Builder 后端（含 story catalog 配置）已退休，
因此本脚本改为校验 **current V4 产品面**：装配成功 + 只暴露登记过的 API 路径。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novelforge.api.app import create_app

CURRENT_API_PREFIXES = (
    "/api/health",
    "/api/story-builder/novels",
    "/api/story-builder/canon",
    "/api/story-builder/editor",
    "/api/story-builder/delivery",
    "/api/story-builder/studio",
    "/api/story-builder/agent",
)


def main():
    app = create_app(ROOT)
    paths = [route.path for route in app.routes if route.path.startswith("/api/")]
    offenders = [path for path in paths
                 if not any(path.startswith(prefix) for prefix in CURRENT_API_PREFIXES)]
    assert offenders == [], f"未登记的 API 路径：{offenders}"
    assert not any("handoffs" in path for path in paths)
    print(f"NovelForge story studio: PASS（{len(paths)} 个 API 路径）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
