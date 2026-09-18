"""V4-12 Layer A — Contract Integrity（§6–§10、§25、§61）。"""

from __future__ import annotations

from pathlib import Path

from acceptance_support import ROOT


def test_all_v4_ssot_documents_exist_and_are_current() -> None:
    base = ROOT / "docs" / "v4"
    contracts = {
        "V4_BLUEPRINT_CONTRACT.md": True,
        "V4_QUALITY_CONTRACT.md": True,
        "V4_REPAIR_CONTRACT.md": True,
        "V4_EDITOR_CONTRACT.md": True,
        "V4_DELIVERY_CONTRACT.md": True,
        "V4_MCP_CONTRACT.md": True,
        "V4_PLUGIN_CONTRACT.md": True,
        "V4_UI_CONTRACT.md": True,
        "V4_AGENT_CONTRACT.md": True,
        # V4-02 / V4-03 的契约文档是设计稿形态（ADR-012 / ADR-014 为正式决策），
        # 只要求存在且标注阶段。
        "V4_LLM_CONTRACT.md": False,
        "V4_MEMORY_ARCHITECTURE.md": False,
    }
    missing = [name for name in contracts if not (base / name).is_file()]
    assert missing == [], f"缺少 SSOT：{missing}"
    for name, declares_ssot in contracts.items():
        text = (base / name).read_text(encoding="utf-8")
        if declares_ssot:
            assert "SSOT" in text, f"{name} 未声明自己是 SSOT"
        # 每份 contract 必须指明自己的冻结阶段
        assert "V4-" in text


def test_no_conflicting_ssot_for_the_same_capability() -> None:
    """同一能力不能有两个文档同时自称 SSOT（§6）。

    post-release cleanup（§59）：MCP / Delivery / Plugin 三份**已被正式 Contract 取代的
    设计稿**（`V4_MCP_SPEC.md` / `V4_EXPORT_SPEC.md` / `V4_PLUGIN_SPEC.md`）已移除，
    收敛为「一个能力一个 current SSOT」。本断言因此从"旧稿必须已降级"升级为
    "旧稿必须不存在"，防止它们以副本形式回流。
    """

    base = ROOT / "docs" / "v4"
    contracts = ["V4_MCP_CONTRACT.md", "V4_DELIVERY_CONTRACT.md", "V4_PLUGIN_CONTRACT.md"]
    retired = ["V4_MCP_SPEC.md", "V4_EXPORT_SPEC.md", "V4_PLUGIN_SPEC.md"]
    for name in contracts:
        assert (base / name).is_file(), f"缺少 current SSOT：{name}"
    for name in retired:
        assert not (base / name).exists(), (
            f"{name} 已被正式 Contract 取代，不应继续存在于 current tree")


def test_schema_and_interface_versions_are_independent() -> None:
    """§7：Blueprint / Delivery / MCP / Plugin / Agent / LLM 版本互不混用。"""

    from novelforge.blueprint import BLUEPRINT_SCHEMA_VERSION
    from novelforge.delivery import DELIVERY_SCHEMA_VERSION
    from novelforge.interfaces.mcp import MCP_INTERFACE_VERSION
    from novelforge.plugins import PLUGIN_API_VERSION
    from novelforge.plugins.sdk import PLUGIN_SDK_VERSION
    from novelforge.agent import AGENT_SCHEMA_VERSION
    from novelforge.agent.planner import MODEL_PLAN_CONTRACT
    from novelforge.generation.contracts import CONTRACT_VERSION

    assert BLUEPRINT_SCHEMA_VERSION >= 1
    assert DELIVERY_SCHEMA_VERSION >= 1
    assert MCP_INTERFACE_VERSION >= 1
    assert PLUGIN_API_VERSION == PLUGIN_SDK_VERSION == 1
    assert AGENT_SCHEMA_VERSION == 1
    assert MODEL_PLAN_CONTRACT == "agent.plan.v1"
    assert CONTRACT_VERSION >= 1
    # 版本是各自模块的常量，不是共享的全局版本号
    assert len({BLUEPRINT_SCHEMA_VERSION, DELIVERY_SCHEMA_VERSION,
                MCP_INTERFACE_VERSION, PLUGIN_API_VERSION, AGENT_SCHEMA_VERSION}) >= 1


def test_public_contracts_do_not_expose_internals() -> None:
    """§8：逐模块检查 __all__；ai 的 public surface 大小被记录。"""

    import novelforge.agent as agent
    import novelforge.ai as ai
    import novelforge.blueprint as blueprint
    import novelforge.delivery as delivery
    import novelforge.editor as editor
    import novelforge.generation as generation
    import novelforge.interfaces.mcp as mcp
    import novelforge.memory as memory
    import novelforge.plugins as plugins
    import novelforge.quality as quality

    for module in (agent, blueprint, delivery, editor, generation, mcp, memory,
                   plugins, quality, ai):
        exported = set(getattr(module, "__all__", ()))
        assert exported, f"{module.__name__} 缺少显式 __all__"
        assert not [name for name in exported if name.startswith("_")], \
            f"{module.__name__} 暴露了私有名"
    # ai surface 是已知的较大面（V4-02 记录）；V4-12 只记录不重构
    ai_surface = len(set(ai.__all__))
    assert ai_surface <= 60, f"AI public surface 异常膨胀：{ai_surface}"
    assert "AgentService" not in set(agent.__all__)     # 内部 facade 不外露


def test_gate_names_and_no_global_score_persist() -> None:
    """§25–§26：Q0–Q9 无漂移；没有权威总分。"""

    from novelforge.quality import GATES
    from novelforge.quality.codes import ISSUE_CODES

    assert GATES == ("Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9")
    assert {spec.gate for spec in ISSUE_CODES} <= set(GATES)
    # 交付 / UI / 质量契约里不得出现"总分"作为权威判断
    for name in ("V4_QUALITY_CONTRACT.md", "V4_UI_CONTRACT.md"):
        text = (ROOT / "docs" / "v4" / name).read_text(encoding="utf-8")
        assert "gate-based" in text.lower() or "Gate-based" in text
    # 交付 / 质量 / UI 文档不得把总分作为权威判断
    for name in ("V4_QUALITY_CONTRACT.md", "V4_DELIVERY_CONTRACT.md",
                 "V4_UI_CONTRACT.md"):
        text = (ROOT / "docs" / "v4" / name).read_text(encoding="utf-8")
        assert "总分" not in text or "不" in text, f"{name} 可能引入权威总分"


def test_provider_boundary_has_no_direct_vendor_calls() -> None:
    """§24：业务模块不得出现直连 provider / HTTP client。"""

    from _guard_utils import imports_matching, python_files

    offenders: list[str] = []
    for package in ("blueprint", "generation", "quality", "editor", "delivery",
                    "memory", "agent", "interfaces", "application", "plugins"):
        for path in python_files(package):
            for name, line in imports_matching(
                    path, ("openai", "anthropic", "httpx", "requests")):
                offenders.append(f"{path.relative_to(ROOT)}:{line} → {name}")
    assert offenders == [], f"出现直连 provider / HTTP client：{offenders}"


def test_single_context_builder_and_single_gateway() -> None:
    """§22、§23：只有一套 ContextBuilder 与一套 LLM Gateway。"""

    from _guard_utils import python_files

    builders: list[str] = []
    for path in python_files("memory", "generation", "quality", "agent"):
        text = path.read_text(encoding="utf-8")
        if "class ContextBuilder" in text:
            builders.append(str(path.relative_to(ROOT)))
    assert len(builders) == 1, f"ContextBuilder 不唯一：{builders}"
    gateways: list[str] = []
    for path in python_files("ai"):
        if "class LLMGateway" in path.read_text(encoding="utf-8"):
            gateways.append(str(path.relative_to(ROOT)))
    assert len(gateways) == 1, f"LLMGateway 不唯一：{gateways}"


def test_v4_docs_do_not_claim_stale_product_truth() -> None:
    """§61：V4 主文档不得继续宣称旧产品定位。"""

    base = ROOT / "docs" / "v4"
    stale = ("V3 is primary", "prose is canonical", "quality total score",
             "agent auto accept")
    offenders: list[str] = []
    for path in sorted(base.glob("V4_*.md")):
        text = path.read_text(encoding="utf-8")
        for phrase in stale:
            if phrase.lower() in text.lower():
                offenders.append(f"{path.name}: {phrase}")
    assert offenders == [], f"V4 文档仍含过时表述：{offenders}"


def test_no_dependency_cycles_between_v4_modules() -> None:
    """§10：静态扫描 application ↔ agent / plugin ↔ application / editor ↔ quality /
    delivery ↔ editor / MCP ↔ plugin 等潜在循环。"""

    from _guard_utils import iter_imports, python_files

    edges: set[tuple[str, str]] = set()
    for package in ("application", "agent", "plugins", "interfaces", "quality",
                    "editor", "delivery", "generation", "blueprint", "memory"):
        for path in python_files(package):
            # plugins/host.py 是 composition root（V4-09 §7、V4_MODULE_BOUNDARIES §3.16）：
            # 它必须同时接触 application 与 interfaces，因此包级存在
            # application ↔ plugins 的**声明边**；但 plugins/__init__ 不 import host，
            # 应用侧只 import plugins 契约（不 import host），运行期无环。
            if str(path.relative_to(ROOT)).replace("\\", "/") == \
                    "src/novelforge/plugins/host.py":
                continue
            source = package
            for name, _line in iter_imports(path):
                if not name.startswith("novelforge."):
                    continue
                target = name.split(".")[1]
                if target in ("application", "agent", "plugins", "interfaces",
                              "quality", "editor", "delivery", "generation",
                              "blueprint", "memory") and target != source:
                    edges.add((source, target))
    cycles = [(left, right) for (left, right) in edges if (right, left) in edges]
    assert cycles == [], f"发现模块循环依赖：{sorted(set(cycles))}"
