"""V4.0.1 Skill Library validator（documentation/tooling baseline）。

用途（见 `skills/novelforge-v4.0.1/README.md`）：

```text
1 catalog integrity        skill id 唯一、catalog ↔ 目录一致、module README 存在
2 skill schema             front matter + 必备章节齐全
3 REST references          每个 `METHOD /path` 都能在真实 FastAPI route 表里找到
4 MCP references           每个 tool / resource 引用都在真实 registry 里
5 source references        每个源码 / 文档 / 测试路径真实存在
6 frozen baseline          SKILL_MANIFEST.json 的 sha256（CRLF 归一化后）一致
```

用法：

```bash
python scripts/validate_v4_0_1_skills.py                 # 校验（CI / 测试使用）
python scripts/validate_v4_0_1_skills.py --write-manifest # 重建哈希基线（需显式说明原因）
```

本脚本不改 runtime、不写 runtime artifact；只有 `--write-manifest` 会写
`skills/novelforge-v4.0.1/SKILL_MANIFEST.json`。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "novelforge-v4.0.1"
MANIFEST_PATH = SKILL_ROOT / "SKILL_MANIFEST.json"

#: capability modules（§22）：workflows 是组合层，其余是能力 owner
MODULES: tuple[str, ...] = (
    "project", "studio", "blueprint", "generation", "memory", "quality", "repair",
    "editor", "delivery", "canon", "story-state", "plugins", "agent", "mcp", "ai",
    "workflows",
)

REQUIRED_SECTIONS: tuple[str, ...] = (
    "## Purpose", "## Use when", "## Do not use when", "## Preconditions",
    "## Required inputs", "## Authoritative interfaces", "## Procedure",
    "## Expected result", "## Verification", "## Common failures",
    "## Safety / invariants", "## Side effects", "## Related skills",
    "## Source references",
)

#: 明确不允许作为 current 能力出现的 retired 标记（§12、§90）
RETIRED_MARKERS: tuple[str, ...] = (
    "route_lab", "v3_projection", "writer bundle", "generate_draft", "continue_draft",
    "rewrite_text", "write_chapter", "CommandCenter", "GuidedFlow", "design_tree",
    "DesignTree", "legacy/writer", "story_builder_routes",
)

SKILL_ID_RE = re.compile(r"novelforge-v4\.0\.1\.[a-z][a-z0-9-]*\.[a-z0-9-]+")
REST_RE = re.compile(
    r"\b(GET|POST|PATCH|PUT|DELETE)\s+"
    r"(/api/[A-Za-z0-9_\-{}/:<>]+|/(?:studio|editor|delivery|agent|canon|novels|health)"
    r"[A-Za-z0-9_\-{}/:<>]*|/(?![A-Za-z0-9_{<]))")
TOOL_REF_RE = re.compile(
    r"\b(generate_[a-z_]+|[a-z_]+_blueprint_node|accept_revision|reject_revision"
    r"|restore_revision|diff_revisions|evaluate_blueprint|plan_repair|repair_issue"
    r"|verify_repair|validate_delivery|create_delivery_snapshot|deliver_blueprint"
    r"|patch_node|rewrite_node|regenerate_node|inspect_blueprint|request_accept)\b")
URI_RE = re.compile(r"novelforge://[^\s`|)\"'，。；、（）【】《》]+")
PATH_RE = re.compile(
    r"\b(?:src|tests|docs|ui|scripts|novel)/[A-Za-z0-9_./\-*]+\.(?:py|md|tsx|ts|json|cjs|yaml|yml)")

#: 作者运行数据（gitignored）路径：允许引用但不要求存在（见 AGENTS.md §24）
RUNTIME_PATH_PREFIXES: tuple[str, ...] = (
    "novel/authoring/",
    "workspace/",
)

_PLACEHOLDER_RE = re.compile(r"[<{][^>}]*[>}]")

#: 名字与 MCP tool 形似、但其实是 Application / 业务方法的 token（允许出现）
NON_MCP_METHOD_TOKENS: frozenset[str] = frozenset({
    "generate_task",     # BlueprintService.generate_task
})

#: 文档化、但由 Host 适配器在运行时注册的资源命名空间（不在 Core 静态 registry 内）
RUNTIME_RESOURCE_PREFIXES: tuple[str, ...] = (
    "novelforge://plugins/",   # 插件资源（kind = plugin_resource:<plugin_id>）
)


class ValidationError(RuntimeError):
    """validator 失败（消息面向修复者）。"""


# --------------------------------------------------------------------- helpers

def normalise_bytes(path: Path) -> bytes:
    """CRLF 归一化后再哈希（仓库在 Windows 上会做 autocrlf 转换）。"""

    return path.read_bytes().replace(b"\r\n", b"\n")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(normalise_bytes(path)).hexdigest()


def read_text(path: Path) -> str:
    return normalise_bytes(path).decode("utf-8")


def skill_files() -> list[Path]:
    return sorted(SKILL_ROOT.glob("*/*/SKILL.md"))


def module_readmes() -> list[Path]:
    return sorted(SKILL_ROOT.glob("*/README.md"))


def manifest_entries() -> list[Path]:
    """需要纳入哈希基线的文件（§61）。"""

    rows = list(skill_files()) + module_readmes()
    for name in ("README.md", "SKILL_CATALOG.md", "SOURCE_MAP.md", "DEPENDENCY_MAP.md",
                 "manifest.yaml"):
        path = SKILL_ROOT / name
        if path.is_file():
            rows.append(path)
    return sorted(rows)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def skill_id_of(path: Path) -> str:
    module, skill = path.parent.parent.name, path.parent.name
    return f"novelforge-v4.0.1.{module}.{skill}"


def _normalise_route(method: str, raw_path: str) -> tuple[str, str]:
    path = raw_path.split("?")[0].strip()
    path = re.sub(r":[A-Za-z_]+", "", path)
    path = _PLACEHOLDER_RE.sub("{}", path)
    if path != "/" and not path.startswith("/api"):
        path = "/api/story-builder" + path
    if len(path) > 1:
        path = path.rstrip("/")
    return method, path


def _normalise_uri(uri: str) -> str:
    return _PLACEHOLDER_RE.sub("{}", uri.rstrip(".,;:）)】") + "").rstrip("/") or "/"


def real_routes() -> set[tuple[str, str]]:
    sys.path.insert(0, str(ROOT / "src"))
    from novelforge.api.app import create_app  # noqa: PLC0415 - 延迟导入以便校验脚本独立运行

    app = create_app(ROOT)
    rows: set[tuple[str, str]] = set()
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        for method in methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            rows.add(_normalise_route(method, route.path))
    return rows


def real_mcp_surface() -> tuple[set[str], set[str]]:
    sys.path.insert(0, str(ROOT / "src"))
    from novelforge.interfaces.mcp.resources import build_resource_registry  # noqa: PLC0415
    from novelforge.interfaces.mcp.tools import build_tool_registry  # noqa: PLC0415

    tools = {spec.name for spec in build_tool_registry().specs()}
    resources = {_normalise_uri(spec.uri) for spec in build_resource_registry().specs()}
    return tools, resources


def agent_actions() -> set[str]:
    """Agent action 名字（plan 预览里出现，不是 MCP tool）。"""

    sys.path.insert(0, str(ROOT / "src"))
    from novelforge.agent.registry import allowlisted_actions  # noqa: PLC0415

    return set(allowlisted_actions())


# ------------------------------------------------------------------ validations

def check_layout() -> None:
    for module in MODULES:
        directory = SKILL_ROOT / module
        if not directory.is_dir():
            raise ValidationError(f"缺少 capability module 目录：{rel(directory)}")
        if not (directory / "README.md").is_file():
            raise ValidationError(f"module 缺少 README（Public Contract）：{rel(directory)}")


def check_skill_schema(path: Path) -> str:
    text = read_text(path)
    skill_id = skill_id_of(path)
    if not text.startswith("---\n"):
        raise ValidationError(f"{rel(path)}：SKILL.md 必须以 YAML front matter 开头")
    head, _, body = text[3:].partition("\n---\n")
    name_line = next((line for line in head.splitlines()
                      if line.strip().startswith("name:")), "")
    if name_line.split(":", 1)[-1].strip() != skill_id:
        raise ValidationError(
            f"{rel(path)}：front matter name 必须是 {skill_id}（实际 {name_line!r}）")
    if not any(line.strip().startswith("description:") for line in head.splitlines()):
        raise ValidationError(f"{rel(path)}：front matter 缺少 description")
    if f"- **Skill ID**: `{skill_id}`" not in body:
        raise ValidationError(f"{rel(path)}：正文缺少 `- **Skill ID**: `{skill_id}``")
    missing = [section for section in REQUIRED_SECTIONS if section not in body]
    if missing:
        raise ValidationError(f"{rel(path)}：缺少必备章节 {missing}")
    for marker in RETIRED_MARKERS:
        if marker in body:
            raise ValidationError(
                f"{rel(path)}：出现 retired 标记 {marker!r}（V2/V3 能力不得作为 current）")
    return skill_id


def check_catalog(skill_ids: set[str]) -> None:
    catalog = SKILL_ROOT / "SKILL_CATALOG.md"
    if not catalog.is_file():
        raise ValidationError("缺少 SKILL_CATALOG.md")
    listed = set(SKILL_ID_RE.findall(read_text(catalog)))
    # catalog 里首次出现的完整 ID 与目录里的 skill 必须一致（工作流表格里 ID 完整写出）
    missing = sorted(skill_ids - listed)
    if missing:
        raise ValidationError(f"SKILL_CATALOG.md 未列出：{missing}")
    unknown = sorted(listed - skill_ids)
    if unknown:
        raise ValidationError(f"SKILL_CATALOG.md 列出不存在的 skill：{unknown}")


def check_skill_id_references(skill_ids: set[str]) -> None:
    for path in skill_files() + module_readmes():
        referenced = set(SKILL_ID_RE.findall(read_text(path)))
        unknown = sorted(referenced - skill_ids)
        if unknown:
            raise ValidationError(f"{rel(path)}：引用不存在的 skill id {unknown}")


def check_rest_references(routes: set[tuple[str, str]]) -> None:
    for path in skill_files() + module_readmes():
        for method, raw in REST_RE.findall(read_text(path)):
            if _normalise_route(method, raw) not in routes:
                raise ValidationError(
                    f"{rel(path)}：REST 引用不存在 → {method} {raw}")


def check_mcp_references(tools: set[str], resources: set[str]) -> None:
    seen_tools: set[str] = set()
    actions = agent_actions()
    for path in skill_files() + module_readmes():
        text = read_text(path)
        for token in TOOL_REF_RE.findall(text):
            if token in tools:
                seen_tools.add(token)
                continue
            if token in actions:
                # Agent action（不是 MCP tool）；plan 预览里合法出现
                continue
            if token in NON_MCP_METHOD_TOKENS:
                continue
            raise ValidationError(f"{rel(path)}：MCP tool 引用未注册 → {token}")
        for uri in URI_RE.findall(text):
            if uri.startswith(RUNTIME_RESOURCE_PREFIXES):
                continue
            if _normalise_uri(uri) not in resources:
                raise ValidationError(f"{rel(path)}：MCP resource 引用未注册 → {uri}")
    missing = sorted(tools - seen_tools)
    if missing:
        raise ValidationError(f"以下 MCP tool 未被任何 skill 覆盖：{missing}")


def check_source_references() -> None:
    for path in skill_files() + module_readmes() + [SKILL_ROOT / "SOURCE_MAP.md"]:
        for raw in PATH_RE.findall(read_text(path)):
            if raw.startswith(RUNTIME_PATH_PREFIXES):
                continue
            if "*" in raw:
                if not list(ROOT.glob(raw)):
                    raise ValidationError(f"{rel(path)}：glob 无匹配 → {raw}")
                continue
            if not (ROOT / raw).exists():
                raise ValidationError(f"{rel(path)}：源码 / 文档 / 测试路径不存在 → {raw}")


def check_source_map(skill_ids: set[str]) -> None:
    source_map = SKILL_ROOT / "SOURCE_MAP.md"
    if not source_map.is_file():
        raise ValidationError("缺少 SOURCE_MAP.md")
    text = read_text(source_map)
    rows = set(re.findall(r"\|\s*`([a-z-]+\.[a-z0-9-]+)`\s*\|", text))
    expected = {skill_id[len("novelforge-v4.0.1."):] for skill_id in skill_ids}
    missing = sorted(expected - rows)
    if missing:
        raise ValidationError(f"SOURCE_MAP.md 缺少行：{missing}")
    unknown = sorted(rows - expected)
    if unknown:
        raise ValidationError(f"SOURCE_MAP.md 出现未知 skill：{unknown}")


def check_manifest() -> None:
    if not MANIFEST_PATH.is_file():
        raise ValidationError("缺少 SKILL_MANIFEST.json（用 --write-manifest 生成）")
    payload = json.loads(read_text(MANIFEST_PATH))
    recorded = {row["path"]: row["sha256"] for row in payload["files"]}
    expected_paths = {rel(path) for path in manifest_entries()}
    missing = sorted(expected_paths - set(recorded))
    if missing:
        raise ValidationError(f"SKILL_MANIFEST.json 缺少文件：{missing}")
    drifted: list[str] = []
    for path in manifest_entries():
        if sha256_of(path) != recorded.get(rel(path)):
            drifted.append(rel(path))
    if drifted:
        raise ValidationError(
            "V4.0.1 baseline 漂移（需显式 SKILL_BASELINE_UPDATE）：" + ", ".join(drifted))


def write_manifest() -> None:
    files = []
    for path in manifest_entries():
        module = path.parent.parent.name if path.name == "SKILL.md" else ""
        skill_id = skill_id_of(path) if path.name == "SKILL.md" else ""
        files.append({"path": rel(path), "module": module, "skill_id": skill_id,
                      "sha256": sha256_of(path)})
    payload = {
        "product": "NovelForge",
        "version": "4.0.1",
        "skill_library_version": "novelforge-v4.0.1",
        "skill_schema_version": 1,
        "hash_algorithm": "sha256",
        "hash_input": "file bytes with CRLF normalised to LF",
        "status": "frozen-baseline",
        "module_count": len(MODULES),
        "skill_count": len(skill_files()),
        "files": files,
    }
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print(f"wrote {rel(MANIFEST_PATH)}（{len(files)} files）")


def validate() -> None:
    check_layout()
    skill_ids = {check_skill_schema(path) for path in skill_files()}
    if len(skill_ids) != len(skill_files()):
        raise ValidationError("skill id 不唯一")
    check_catalog(skill_ids)
    check_source_map(skill_ids)
    check_skill_id_references(skill_ids)
    check_rest_references(real_routes())
    tools, resources = real_mcp_surface()
    check_mcp_references(tools, resources)
    check_source_references()
    check_manifest()
    print(f"novelforge-v4.0.1 skills: PASS"
          f"（{len(skill_ids)} skills / {len(MODULES)} modules / "
          f"{len(tools)} MCP tools / {len(resources)} MCP resources）")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate novelforge-v4.0.1 skills")
    parser.add_argument("--write-manifest", action="store_true",
                        help="重建 SKILL_MANIFEST.json（baseline update，需说明原因）")
    args = parser.parse_args(argv)
    try:
        if args.write_manifest:
            write_manifest()
            return 0
        validate()
    except ValidationError as exc:
        print(f"novelforge-v4.0.1 skills: FAIL — {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
