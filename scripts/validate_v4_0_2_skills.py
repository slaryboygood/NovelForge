"""V4.0.2 Skill Baseline validator（增量继承 V4.0.1）。

```text
生效集合 = skills/novelforge-v4.0.1/**（base，未改动）
         ∪ skills/novelforge-v4.0.2/**（overrides，同路径替换）
```

校验内容：

```text
1 base integrity      V4.0.1 SKILL_MANIFEST.json 的哈希与磁盘一致（基线未被改动）
2 override integrity  每个 override 相对路径在 V4.0.1 里存在（同路径替换，不新增 skill 目录）
3 skill schema        front matter name == novelforge-v4.0.2.<module>.<skill> + 必备章节 + retired 守卫
4 REST references     引用的端点存在于真实 route 表
5 MCP references      引用的 tool / resource 存在于真实 registry
6 source references   引用的源码 / 文档 / 测试路径存在
7 skill id refs       引用的 skill id ∈ (V4.0.2 overrides ∪ V4.0.1 已发布 skill)
8 closure evidence    三个 P0 回归测试存在（PB-1 / PB-2 / PB-3）
9 hash baseline       skills/novelforge-v4.0.2/SKILL_MANIFEST.json 与磁盘一致
```

用法：

```bash
python scripts/validate_v4_0_2_skills.py                  # 校验
python scripts/validate_v4_0_2_skills.py --write-manifest  # 重建哈希基线（需说明原因）
```
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB_ROOT = ROOT / "skills" / "novelforge-v4.0.2"
BASE_ROOT = ROOT / "skills" / "novelforge-v4.0.1"
BASE_MANIFEST = BASE_ROOT / "SKILL_MANIFEST.json"
MANIFEST_PATH = LIB_ROOT / "SKILL_MANIFEST.json"
ID_PREFIX = "novelforge-v4.0.2."

#: 三个 P0 的回归证据（少一个就说明"修了但没固化"）
CLOSURE_TESTS: tuple[str, ...] = (
    "tests/delivery/test_delivery_historical_quality.py",
    "tests/agent/test_agent_approval_lifecycle.py",
    "tests/mcp/test_mcp_stdio_entrypoint.py",
)


class ValidationError(RuntimeError):
    """V4.0.2 baseline 校验失败。"""


def _load_base():
    spec = importlib.util.spec_from_file_location(
        "novelforge_v4_0_1_validator", ROOT / "scripts" / "validate_v4_0_1_skills.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def normalise_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(normalise_bytes(path)).hexdigest()


def read_text(path: Path) -> str:
    return normalise_bytes(path).decode("utf-8")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def lib_files() -> list[Path]:
    return sorted(path for path in LIB_ROOT.rglob("*") if path.is_file()
                  and path.name != MANIFEST_PATH.name)


def override_relpaths() -> list[str]:
    """本目录相对 V4.0.1 根的路径（= override 路径）。"""

    return sorted(str(path.relative_to(LIB_ROOT)).replace("\\", "/")
                  for path in lib_files())


def skill_id_of(path: Path) -> str:
    return f"{ID_PREFIX}{path.parent.parent.name}.{path.parent.name}"


# ------------------------------------------------------------------ checks
def check_base_integrity() -> None:
    if not BASE_MANIFEST.is_file():
        raise ValidationError(f"缺少 V4.0.1 baseline manifest：{rel(BASE_MANIFEST)}")
    payload = json.loads(read_text(BASE_MANIFEST))
    drifted = [row["path"] for row in payload["files"]
               if sha256_of(ROOT / row["path"]) != row["sha256"]]
    if drifted:
        raise ValidationError(
            "V4.0.1 baseline 被改动（V4.0.2 只能覆盖，不能改历史）：" + ", ".join(drifted))


def check_overrides_exist_in_base() -> None:
    missing = [raw for raw in override_relpaths()
               if not (BASE_ROOT / raw).exists()]
    if missing:
        raise ValidationError(
            "override 路径在 V4.0.1 里不存在（只能是同路径替换）：" + ", ".join(missing))


def check_skill_schema(base: object) -> set[str]:
    ids: set[str] = set()
    for path in sorted(LIB_ROOT.glob("*/*/SKILL.md")):
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
        if not any(line.strip().startswith("description:")
                   for line in head.splitlines()):
            raise ValidationError(f"{rel(path)}：front matter 缺少 description")
        if f"- **Skill ID**: `{skill_id}`" not in body:
            raise ValidationError(f"{rel(path)}：正文缺少 skill id 行")
        missing = [section for section in base.REQUIRED_SECTIONS if section not in body]
        if missing:
            raise ValidationError(f"{rel(path)}：缺少必备章节 {missing}")
        for marker in base.RETIRED_MARKERS:
            if marker in body:
                raise ValidationError(
                    f"{rel(path)}：出现 retired 标记 {marker!r}（V2/V3 能力不得作为 current）")
        ids.add(skill_id)
    if not ids:
        raise ValidationError("没有找到任何 V4.0.2 SKILL.md")
    return ids


def check_rest_references(base: object) -> int:
    routes = base.real_routes()
    hits = 0
    for path in lib_files():
        if path.suffix != ".md":
            continue
        for method, raw in base.REST_RE.findall(read_text(path)):
            hits += 1
            if base._normalise_route(method, raw) not in routes:
                raise ValidationError(
                    f"{rel(path)}：REST 引用不存在 → {method} {raw}")
    return hits


def check_mcp_references(base: object) -> None:
    tools, resources = base.real_mcp_surface()
    actions = base.agent_actions()
    patterns = _resource_instance_patterns()
    for path in lib_files():
        if path.suffix != ".md":
            continue
        text = read_text(path)
        for token in base.TOOL_REF_RE.findall(text):
            if token in tools or token in actions:
                continue
            if token in base.NON_MCP_METHOD_TOKENS:
                continue
            raise ValidationError(f"{rel(path)}：MCP tool 引用未注册 → {token}")
        for uri in base.URI_RE.findall(text):
            if uri.startswith(base.RUNTIME_RESOURCE_PREFIXES):
                continue
            if base._normalise_uri(uri) in resources:
                continue
            # 具体实例（例如 novelforge://novels/studio_clean）也允许：只要匹配某个模板
            if any(pattern.match(uri.split("?")[0]) for pattern in patterns):
                continue
            if True:
                raise ValidationError(f"{rel(path)}：MCP resource 引用未注册 → {uri}")


def _resource_instance_patterns() -> list[re.Pattern[str]]:
    """把 registry 里的 resource 模板转成"具体实例"匹配器（文档可以写真实 id）。"""

    from novelforge.interfaces.mcp.resources import build_resource_registry

    patterns: list[re.Pattern[str]] = []
    for spec in build_resource_registry().specs():
        segments = str(spec.uri).split("/")
        parts = ["[^/]+" if segment.startswith("{") and segment.endswith("}")
                 else re.escape(segment) for segment in segments]
        patterns.append(re.compile("^" + "/".join(parts) + "$"))
    return patterns


def check_source_references(base: object) -> None:
    for path in lib_files():
        if path.suffix != ".md":
            continue
        for raw in base.PATH_RE.findall(read_text(path)):
            if raw.startswith(base.RUNTIME_PATH_PREFIXES):
                continue
            if "*" in raw:
                if not list(ROOT.glob(raw)):
                    raise ValidationError(f"{rel(path)}：glob 无匹配 → {raw}")
                continue
            if not (ROOT / raw).exists():
                raise ValidationError(f"{rel(path)}：源码 / 文档 / 测试路径不存在 → {raw}")


def _published_v4_0_1_ids(base: object) -> set[str]:
    catalog = read_text(BASE_ROOT / "SKILL_CATALOG.md")
    return set(base.SKILL_ID_RE.findall(catalog))


def check_skill_id_references(base: object, override_ids: set[str]) -> None:
    known = override_ids | _published_v4_0_1_ids(base)
    for path in lib_files():
        if path.suffix != ".md":
            continue
        referenced = set(base.SKILL_ID_RE.findall(read_text(path)))
        unknown = sorted(referenced - known)
        if unknown:
            raise ValidationError(f"{rel(path)}：引用不存在的 skill id {unknown}")


def check_closure_tests() -> None:
    missing = [raw for raw in CLOSURE_TESTS if not (ROOT / raw).is_file()]
    if missing:
        raise ValidationError(f"缺少 P0 回归证据测试：{missing}")


def check_manifest(override_ids: set[str]) -> None:
    if not MANIFEST_PATH.is_file():
        raise ValidationError("缺少 SKILL_MANIFEST.json（用 --write-manifest 生成）")
    payload = json.loads(read_text(MANIFEST_PATH))
    if payload.get("inherits", {}).get("skill_library_version") != "novelforge-v4.0.1":
        raise ValidationError("SKILL_MANIFEST.json 必须声明继承 novelforge-v4.0.1")
    recorded = {row["path"]: row["sha256"] for row in payload["files"]}
    drifted = [rel(path) for path in lib_files()
               if recorded.get(rel(path)) != sha256_of(path)]
    if drifted:
        raise ValidationError(
            "V4.0.2 baseline 漂移（需显式 SKILL_BASELINE_UPDATE）：" + ", ".join(drifted))
    if payload.get("override_count") != len(lib_files()):
        raise ValidationError("SKILL_MANIFEST.json 的 override_count 与磁盘不一致")
    if set(payload.get("skill_ids") or []) != override_ids:
        raise ValidationError("SKILL_MANIFEST.json 的 skill_ids 与磁盘不一致")
    if payload.get("inherits", {}).get("base_manifest_sha256") != sha256_of(BASE_MANIFEST):
        raise ValidationError(
            "SKILL_MANIFEST.json 记录的 V4.0.1 base manifest 哈希与实际不符"
            "（基线被改动或被误更新）")


def write_manifest() -> None:
    base = _load_base()
    override_ids = check_skill_schema(base)
    rows = []
    for path in lib_files():
        raw = str(path.relative_to(LIB_ROOT)).replace("\\", "/")
        if path.name == "SKILL.md":
            module = path.parent.parent.name
        elif path.name == "README.md" and path.parent != LIB_ROOT:
            module = path.parent.name
        else:
            module = ""
        rows.append({"path": rel(path), "relative_path": raw, "module": module,
                     "skill_id": skill_id_of(path) if path.name == "SKILL.md" else "",
                     "override": (BASE_ROOT / raw).exists(),
                     "sha256": sha256_of(path)})
    payload = {
        "product": "NovelForge",
        "version": "4.0.2",
        "skill_library_version": "novelforge-v4.0.2",
        "skill_schema_version": 1,
        "status": "frozen-baseline",
        "release_kind": "bugfix-stabilization",
        "hash_algorithm": "sha256",
        "hash_input": "file bytes with CRLF normalised to LF",
        "inherits": {"skill_library_version": "novelforge-v4.0.1",
                     "root": rel(BASE_ROOT),
                     "base_manifest": rel(BASE_MANIFEST),
                     "base_manifest_sha256": sha256_of(BASE_MANIFEST),
                     "mode": "copy-and-override"},
        "id_namespace": ("override 文件用 novelforge-v4.0.2.*；继承文件保持 "
                         "novelforge-v4.0.1.*（同一份未修改的 skill）"),
        "fixed_defects": ["PB-1", "PB-2", "PB-3"],
        "closure_tests": list(CLOSURE_TESTS),
        "override_count": len(rows),
        "override_files": [row["relative_path"] for row in rows],
        "skill_ids": sorted(override_ids),
        "files": rows,
    }
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print(f"wrote {rel(MANIFEST_PATH)}（{len(rows)} files）")


def validate() -> None:
    base = _load_base()
    check_base_integrity()
    check_overrides_exist_in_base()
    override_ids = check_skill_schema(base)
    check_rest_references(base)
    check_mcp_references(base)
    check_source_references(base)
    check_skill_id_references(base, override_ids)
    check_closure_tests()
    check_manifest(override_ids)
    print(f"novelforge-v4.0.2 skills: PASS"
          f"（{len(override_ids)} override skills / {len(lib_files())} files / "
          f"base=V4.0.1 unchanged）")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate novelforge-v4.0.2 skill delta")
    parser.add_argument("--write-manifest", action="store_true",
                        help="重建 SKILL_MANIFEST.json（baseline update，需说明原因）")
    args = parser.parse_args(argv)
    try:
        if args.write_manifest:
            write_manifest()
            return 0
        validate()
    except ValidationError as exc:
        print(f"novelforge-v4.0.2 skills: FAIL — {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
