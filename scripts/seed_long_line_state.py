"""为 V2-J 三题材长期验证准备长线 StoryState（隔离数据根目录专用）。

用法：
    .venv\\Scripts\\python.exe scripts/seed_long_line_state.py --root <临时目录> --novel <novel_id> --pack <pack_id>

只写入指定数据根目录，不接触作者正在使用的数据。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))


def main() -> int:
    from novelforge.story_builder import StoryBlueprintRepository
    from novelforge.story_engine import NovelProfileRepository

    from test_story_engine_long_lines import seed_long_line

    root = Path(sys.argv[sys.argv.index("--root") + 1]).resolve()
    novel_id = sys.argv[sys.argv.index("--novel") + 1]
    pack_id = sys.argv[sys.argv.index("--pack") + 1]
    profile = NovelProfileRepository(root).load(novel_id)
    blueprint_id = ""
    for path in sorted((root / "novel/authoring/story_builder/blueprints").glob("bp_*")):
        blueprint = StoryBlueprintRepository(root).latest(path.name)
        if blueprint is not None and blueprint.project_id == novel_id:
            blueprint_id = blueprint.blueprint_id
            break
    if not blueprint_id:
        print(f"找不到 {novel_id} 的蓝图", file=sys.stderr)
        return 1
    state = seed_long_line(root, blueprint_id, novel_id, pack_id)
    print(f"seeded {novel_id} pack={pack_id} log={len(state.effect_log)} "
          f"locations={len(state.location.known)} factions={len(state.factions)}")
    del profile
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
