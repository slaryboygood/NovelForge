"""Story Studio 浏览器验收服务（V4-10）。

只用于浏览器门禁：隔离数据根 + **stub 模型**（零网络）+ fixture 插件，
绝不接触作者数据，也绝不调用真实 provider。

```powershell
.venv\\Scripts\\python.exe scripts/studio_ui_test_server.py --port 8040 --root workspace/studio_ui_test_root
```

组装（composition 只发生在这里，app 本身不 import 插件平台）：

```text
stub gateway（novelforge.ai，InMemoryCache + 本地 provider）
        ↓
create_app(root, gateway=..., plugin_host=plugin_host)
```
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (SRC, ROOT / "tests" / "plugins" / "fixtures"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class StubProvider:
    """按脚本返回结构化 JSON 的本地 provider（零网络，测试专用）。"""

    provider_id = "studio-stub"

    def __init__(self, script: Sequence[Any]) -> None:
        self.script = list(script)
        self.requests: list[Any] = []

    @property
    def calls(self) -> int:
        return len(self.requests)

    def complete(self, request: Any) -> Any:
        from novelforge.ai import ProviderResponse

        self.requests.append(request)
        item = self.script.pop(0) if self.script else {}
        text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        return ProviderResponse(text=text, model=request.model,
                                usage_raw={"prompt_tokens": 12, "completion_tokens": 8},
                                finish_reason="stop")


def build_gateway(script: Sequence[Any]) -> Any:
    from novelforge.ai import (
        InMemoryCache, LLMGateway, ModelRouter, ModelSpec, ProviderConfig,
        ProviderRegistry,
    )

    config = ProviderConfig(
        provider_id="stub", kind="openai_compatible",
        base_url="http://stub.local/v1", api_key_env="STUB_KEY", enabled=True,
        default_model="stub-creative",
        models=(ModelSpec(model_id="stub-creative",
                          capabilities=("creative", "structured_output",
                                        "large_context"),
                          cost_tier=4, speed_tier=2, context_tokens=128000),))
    return LLMGateway({"stub": StubProvider(script)},
                      router=ModelRouter(ProviderRegistry([config])),
                      cache=InMemoryCache(), sleep=lambda _s: None,
                      clock=lambda: 0.0)


#: 生成脚本（gate 按 UI 动作顺序消费：premise → world → character → story_arc
#: → structural_unit → chapter → scene）
def generation_script() -> list[Any]:
    return [
        {"premise": "一座断电边城必须在七十二小时内恢复供电",
         "central_conflict": "修复需要牺牲唯一的水源存量",
         "protagonist_goal": "在不牺牲水源的前提下恢复供电",
         "stakes": "全城居民的呼吸维持系统", "dramatic_question": "代价必须有人承担吗",
         "story_promise": "技术困境下的道德选择", "genre": "hard-sf",
         "tone": "冷峻克制", "constraints": ["不得出现超自然力量"]},
        {"rules": ["供电中断超过七十二小时城市将不可居住"],
         "locations": [{"name": "中转站", "note": "旧时代的电力调度核心"},
                       {"name": "水务塔", "note": "全城净水存量"}],
         "factions": [{"name": "修复班", "goal": "恢复供电"},
                      {"name": "水务委", "goal": "保住水源"}],
         "resources": ["备用电池组", "净水存量"],
         "technology_or_magic": ["旧时代的电力调度系统仍在运行"],
         "story_relevant_history": ["十年前的事故让两套系统彼此不信任"]},
        {"name": "林澈", "role": "主角", "goal": "恢复供电",
         "motivation": "父亲死在同一座中转站",
         "need": "学会把决定权交给别人",
         "conflict_source": "必须在两难中做决定",
         "flaw": "宁可信设备不信人", "fear": "再失去一个同伴",
         "misbelief": "只有自己修得好设备", "strength": "熟悉旧设备",
         "story_function": "承担代价并做出选择",
         "relationships": [{"with": "秦默", "kind": "不信任"}]},
        {"initial_state": "城市刚断电", "inciting_incident": "备用电源被人为破坏",
         "progressive_complications": ["许可被撤回", "备用电池组被盗"],
         "midpoint": "发现水源与电力只能保一个",
         "major_turns": ["发现破坏者是内部人"],
         "crisis": "必须在水与电之间做选择", "climax": "把选择权交给全城",
         "resolution": "达成新的分配方案"},
        {"unit_type": "act", "title": "断电之后", "goal": "让读者感到时间压力",
         "conflict": "许可与时间", "turn": "内部破坏暴露",
         "outcome": "主角决定绕过常规流程", "child_units": []},
        {"title": "维修记录里的异常编号", "goal": "确认被删除的日志是否真实存在",
         "pov": "林澈", "characters": [], "location": "station",
         "conflict": "主管拒绝开放旧记录", "turn": "日志编号仍存在于设备缓存",
         "outcome": "获得一条指向水务塔的线索", "hook": "缓存显示最后访问者已死亡",
         "setup": [], "payoff": [],
         "state_change_intent": []},
        {"chapter_id": "", "pov": "林澈", "location": "station", "time": "第三天清晨",
         "scene_purpose": "让主角拿到被删除日志的第一条证据",
         "character_goals": ["拿到日志", "阻止他继续查"],
         "conflict": "主管拒绝开放记录", "escalation": "对手把许可撤回",
         "turn": "缓存在设备里仍保留日志编号", "outcome": "主角获得线索但失去许可",
         "information_reveal": ["日志最后由一个已死亡的人访问"],
         "character_change": "主角决定绕过流程",
         "relationship_change": "与对手的信任进一步下降",
         "setup": [], "payoff": [],
         "state_transition_intent": [],
         "next_hook": "死亡者为什么能访问缓存",
         "story_function": ["advance_plot", "reveal_information", "setup"]},
    ]


def build_plugin_host(root: Path) -> Any:
    """装配一个 fixture 插件（只读展示用；不影响 Core）。"""

    from novelforge.plugins.host import PluginHost

    manifest = root / "fixture-plugin.json"
    manifest.write_text(json.dumps({
        "plugin_id": "com.example.exporter", "name": "示例导出插件",
        "version": "1.0.0", "description": "演示：为交付增加一个文本列表格式",
        "entry_point": "example_exporter_plugin:register",
        "capabilities": ["exporter"], "permissions": ["delivery.export"],
        "author": "novelforge-tests",
    }, ensure_ascii=False), encoding="utf-8")
    host = PluginHost(root, novel_id="", manifest_paths=[manifest])
    host.discover()
    host.service.approve("com.example.exporter")
    host.service.enable("com.example.exporter")
    return host


def seed_clean_novel(root: Path, novel_id: str = "studio_clean") -> str:
    """用 V4-04→V4-07 的 Golden fixture 造一本**已接受 + 质量通过**的作品。

    只服务浏览器门禁（交付下载需要一份真正可交付的快照）；
    它复用测试 fixture 的确定性数据，不接触任何作者数据。
    """

    import importlib.util

    path = ROOT / "tests" / "delivery" / "delivery_support.py"
    if not path.is_file():          # 允许在裁剪过的环境里只跑生成流程
        return ""
    spec = importlib.util.spec_from_file_location("studio_seed_support", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["studio_seed_support"] = module
    spec.loader.exec_module(module)
    module.delivery_stack(root, novel_id=novel_id)
    return novel_id


def main() -> int:
    import uvicorn

    from novelforge.api.app import create_app

    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8040
    data_root = (Path(sys.argv[sys.argv.index("--root") + 1]) if "--root" in sys.argv
                 else ROOT / "workspace" / "studio_ui_test_root")
    data_root.mkdir(parents=True, exist_ok=True)
    for relative in ("novel/config/story_engine", "novel/config/story_builder"):
        source, target = ROOT / relative, data_root / relative
        if source.is_dir() and not target.exists():
            shutil.copytree(source, target)

    gateway = build_gateway(generation_script())
    plugin_host = build_plugin_host(data_root)
    clean_id = seed_clean_novel(data_root)
    app = create_app(data_root, gateway=gateway, plugin_host=plugin_host)
    print(f"[studio-ui-test] root={data_root} clean_novel={clean_id or '—'} "
          f"-> http://127.0.0.1:{port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
