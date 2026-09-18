"""永久守卫：V4-11 agent 模块边界（`docs/v4/V4_MODULE_BOUNDARIES.md` §3.17）。

```text
agent              → core（ids/errors）+ persistence.paths + 自己的 ports
agent              ✗ api / interfaces.mcp / repository / store / provider /
                     HTTP client / 自行拼 artifact path / shell / SQL
各业务模块          ✗ import novelforge.agent（只有 application.services.agent 可以）
interfaces         ✗ import agent internals（只经 application.services.agent）
```
"""

from __future__ import annotations

from pathlib import Path

from _guard_utils import (
    ROOT,
    identifier_names,
    imports_matching,
    iter_imports,
    python_files,
    string_literals,
)

AGENT_FORBIDDEN_PREFIXES = (
    "novelforge.api", "novelforge.interfaces", "novelforge.blueprint",
    "novelforge.quality.store", "novelforge.editor.store", "novelforge.delivery.store",
    "novelforge.ai.providers", "novelforge.memory", "novelforge.generation",
    "novelforge.application", "novelforge.plugins",
    "fastapi", "starlette", "mcp", "httpx", "requests", "urllib", "openai",
    "anthropic", "subprocess", "sqlite3",
)

FORBIDDEN_IDENTIFIERS = (
    "BlueprintRepository", "QualityStore", "EditorStore", "DeliveryStore",
    "RepairExecutor", "RepairPlanner", "LLMGateway", "CanonStore", "StoryStateStore",
)

#: 允许依赖 agent public contract 的模块（application composition）
AGENT_CONSUMERS_ALLOWED = {
    "src/novelforge/application/services/agent.py",
}

#: 这些模块不得 import agent（避免循环依赖 / 反向依赖）
AGENT_REVERSE_FORBIDDEN = (
    "core", "persistence", "story_engine", "story_builder", "ai", "memory",
    "blueprint", "generation", "quality", "editor", "delivery", "plugins",
)


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def test_agent_does_not_import_forbidden_layers() -> None:
    offenders: list[str] = []
    for path in python_files("agent"):
        for name, line in iter_imports(path):
            if name.startswith(AGENT_FORBIDDEN_PREFIXES):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "agent 不得穿透业务内部 / 接口 / provider（§2、§8、§91）：\n"
        + "\n".join(offenders))


def test_agent_only_depends_on_core_and_persistence_paths() -> None:
    offenders: list[str] = []
    for path in python_files("agent"):
        for name, line in iter_imports(path):
            if not name.startswith("novelforge."):
                continue
            if name.startswith(("novelforge.core", "novelforge.persistence")):
                continue
            offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "agent core 只允许依赖 core / persistence.paths：\n" + "\n".join(offenders))


def test_agent_persists_only_through_persistence_paths() -> None:
    offenders: list[str] = []
    for path in python_files("agent"):
        for value, line in string_literals(path):
            lowered = value.lower()
            if lowered.startswith(("novel/", "novel\\", "workspace/",
                                   "workspace\\")) or "authoring/" in lowered:
                offenders.append(f"{_relative(path)}:{line} → {value!r}")
        text = path.read_text(encoding="utf-8")
        for token in ('Path("novel', "Path('novel"):
            if token in text:
                offenders.append(f"{_relative(path)} → {token}")
    assert offenders == [], (
        "agent 运行数据必须经 persistence.paths（§57）：\n" + "\n".join(offenders))


def test_agent_does_not_construct_business_objects() -> None:
    offenders: list[str] = []
    for path in python_files("agent"):
        names = {name for name, _line in identifier_names(path)}
        hits = sorted(names & set(FORBIDDEN_IDENTIFIERS))
        if hits:
            offenders.append(f"{_relative(path)} → {hits}")
    assert offenders == [], (
        "agent 不得直接构造 / 持有 repository / store / provider：\n"
        + "\n".join(offenders))


def test_agent_has_no_shell_or_dynamic_execution() -> None:
    offenders: list[str] = []
    for path in python_files("agent"):
        text = path.read_text(encoding="utf-8")
        for token in ("eval(", "exec(", "__import__(", "os.system", "importlib"):
            if token in text:
                offenders.append(f"{_relative(path)} → {token}")
    assert offenders == [], (
        "agent 不是通用 computer agent（§23）：\n" + "\n".join(offenders))


def test_business_modules_do_not_import_agent() -> None:
    offenders: list[str] = []
    for package in AGENT_REVERSE_FORBIDDEN:
        for path in python_files(package):
            for name, line in iter_imports(path):
                if name == "novelforge.agent" or name.startswith("novelforge.agent."):
                    offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "业务模块不得依赖 agent（application.services.agent 除外，§9、§92）：\n"
        + "\n".join(offenders))


def test_agent_public_contract_is_small_and_has_no_internals() -> None:
    import novelforge.agent as agent

    exported = set(agent.__all__)
    assert {"AgentGoal", "AgentPolicy", "AgentPlan", "AgentStep", "AgentResult",
            "AgentRun", "AgentCheckpoint", "AgentApprovalRequest",
            "AgentError"} <= exported
    assert not [name for name in exported if name.startswith("_")]
    # application 层 facade 与内部实现不进入 agent public contract
    assert "AgentService" not in exported
    assert "ApplicationReadPort" not in exported


def test_interfaces_only_use_application_agent_facade() -> None:
    offenders: list[str] = []
    for path in python_files("interfaces"):
        for name, line in iter_imports(path):
            if name == "novelforge.agent" or name.startswith("novelforge.agent."):
                offenders.append(f"{_relative(path)}:{line} → {name}")
    assert offenders == [], (
        "interfaces 只能调用 application.services.agent（§64、§97）：\n"
        + "\n".join(offenders))


def test_application_exposes_agent_facade_only() -> None:
    path = ROOT / "src" / "novelforge" / "application" / "services" / "agent.py"
    assert path.is_file(), "application.services.agent 必须存在（唯一入口）"
    text = path.read_text(encoding="utf-8")
    assert "class AgentService" in text
    assert "from .facade import" in text
    # application facade 不得依赖 interfaces
    for name, line in iter_imports(path):
        assert not name.startswith("novelforge.interfaces"), \
            f"application.services.agent:{line} 不得依赖 interfaces"
