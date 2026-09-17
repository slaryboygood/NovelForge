"""验证当前故事构筑产品，不扫描历史小说生产数据。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from novelforge.story_builder import load_story_catalog
from novelforge.api.app import app


def main():
    load_story_catalog(ROOT)
    paths = [route.path for route in app.routes if route.path.startswith("/api/")]
    assert all(path == "/api/health" or path.startswith("/api/story-builder/") for path in paths)
    assert not any("handoffs" in path for path in paths)
    print("NovelForge story-builder: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
