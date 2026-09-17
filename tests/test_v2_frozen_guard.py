"""Frozen Guard（V2 / V3 冻结机制，自包含，默认运行）。

冻结模型已从

    git tag / historical commit must remain resolvable

迁移为

    tracked frozen evidence + cryptographic digest manifest

原因：NovelForge V3 Final 是 V4 的全新单 root 基线。V1 / V2 / V3 的开发历史保存在
经过完整恢复验证的外部 bundle 中（见 `docs/FROZEN_EVIDENCE_MANIFEST.json` 的
`external_archive`），活动 Git 仓库不再承担旧历史的在线寻址职责。

因此本守卫**不再要求** `novelforge-product-v2.0` 之类的旧 tag 或旧 commit 可以解析，
而是验证：

* `docs/FROZEN_EVIDENCE_MANIFEST.json` 存在、结构完整，并把旧 release 明确标注为
  `historical / archived / not an active Git ref`；
* 被冻结资产（`novel/authoring` 的已跟踪文件）的摘要与 manifest 记录一致；
* V3 Final 仍然是单一 root commit（`git rev-list --count HEAD == 1`）；
* 仍作为活动指针引用旧 release 名称的文档，必须标注 historical 语义。

没有 git 元数据（例如导出源码包）时，需要 git 的断言会 skip，而不是 fail。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "docs" / "FROZEN_EVIDENCE_MANIFEST.json"
ACTIVE_RELEASE = "novelforge-product-v3-final"
HISTORICAL_MARKER = "not an active Git ref"


def _manifest() -> dict:
    assert MANIFEST_PATH.is_file(), (
        "缺少冻结证据 manifest：docs/FROZEN_EVIDENCE_MANIFEST.json")
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), "manifest 必须是 JSON 对象"
    return payload


def _git(*args: str) -> tuple[int, str]:
    try:
        done = subprocess.run(("git", *args), cwd=PROJECT_ROOT, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
    except OSError:  # pragma: no cover - 没有 git 可执行文件
        return 127, ""
    return done.returncode, (done.stdout or "").strip()


def _require_git() -> None:
    code, _ = _git("rev-parse", "--git-dir")
    if code != 0:
        pytest.skip("not a git working tree")


def _tracked_files(paths: list[str]) -> list[str]:
    code, out = _git("ls-files", "--", *paths)
    assert code == 0, "无法枚举已跟踪文件"
    return sorted(row for row in out.splitlines() if row.strip())


def _digest_of(files: list[str]) -> str:
    """逐文件 sha256（先做 CRLF -> LF 归一化），再对 `路径:摘要` 行整体 sha256。"""

    rows = []
    for relative in files:
        data = (PROJECT_ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
        rows.append(f"{relative}:{hashlib.sha256(data).hexdigest()}")
    rows.sort()
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- 1
def test_frozen_evidence_manifest_is_well_formed() -> None:
    payload = _manifest()

    assert payload["schema_version"] == 1
    assert payload["manifest_id"] == "NOVELFORGE_FROZEN_EVIDENCE_MANIFEST_V1"
    assert payload["freeze_authority"]["model"] == (
        "tracked frozen evidence + cryptographic digest manifest")

    active = payload["active_release"]
    assert active["name"] == ACTIVE_RELEASE, "活动 release 必须是 V3 Final tag"
    assert active["branch"] == "main"
    assert active["kind"] == "annotated_tag"

    assert payload["active_history_shape"]["root_commit_count"] == 1

    evidence = payload["frozen_evidence"]
    assert evidence, "至少必须有一条冻结证据"
    for row in evidence:
        assert row["paths"], f"{row['evidence_id']}: 必须声明被保护的路径"
        assert row["digest"], f"{row['evidence_id']}: 必须记录摘要"
        assert row["file_count"] > 0
        assert "sha256" in row["algorithm"]
        assert "CRLF" in row["normalization"]

    archive = payload["external_archive"]
    assert archive["history_bundle_verified"] is True
    assert archive["history_bundle"].endswith(".bundle")


# --------------------------------------------------------------------------- 2
def test_historical_releases_are_metadata_only() -> None:
    payload = _manifest()
    rows = payload["historical_releases"]
    assert rows, "必须记录历史 release 元数据"

    for row in rows:
        assert row["name"]
        assert len(row["commit"]) == 40, f"{row['name']}: 必须记录完整 commit hash"
        assert HISTORICAL_MARKER in row["status"], (
            f"{row['name']}: 状态必须标注 {HISTORICAL_MARKER!r}")

    policy = payload["historical_reference_policy"]
    assert policy["marker"] == HISTORICAL_MARKER
    assert policy["checked_documents"], "必须声明需要标注 historical 语义的文档"

    names = {row["name"] for row in rows}
    assert ACTIVE_RELEASE not in names, "活动 release 不能同时出现在历史列表里"


# --------------------------------------------------------------------------- 3
def test_frozen_evidence_digest_matches_tracked_files() -> None:
    """冻结资产漂移守卫：不依赖任何历史 commit / tag。"""

    _require_git()
    payload = _manifest()

    for row in payload["frozen_evidence"]:
        files = _tracked_files(row["paths"])
        assert len(files) == row["file_count"], (
            f"{row['evidence_id']}: 已跟踪文件数变化 {len(files)} != {row['file_count']}"
            "（冻结资产发生增删；如需变更请显式更新 manifest，而不是放宽断言）")
        assert _digest_of(files) == row["digest"], (
            f"{row['evidence_id']}: 冻结资产摘要不一致（被改动过）")


# --------------------------------------------------------------------------- 4
def test_history_is_a_single_root_commit() -> None:
    _require_git()
    payload = _manifest()
    expected = payload["active_history_shape"]["root_commit_count"]

    code, text = _git("rev-list", "--count", "HEAD")
    assert code == 0, "无法读取当前历史"
    assert int(text) == expected, (
        f"V3 Final 必须保持单一 root commit（实际 commit 数 {text}）")

    code, roots = _git("rev-list", "--max-parents=0", "HEAD")
    assert code == 0
    assert len([row for row in roots.splitlines() if row.strip()]) == 1


# --------------------------------------------------------------------------- 5
def test_old_release_refs_are_not_required_to_resolve() -> None:
    """旧 release 只作为 metadata：本 guard 不要求 Git 能解析它们。"""

    _require_git()
    payload = _manifest()

    for row in payload["historical_releases"]:
        name = row["name"]
        code, _ = _git("rev-parse", "--verify", "--quiet", f"refs/tags/{name}")
        if code != 0:
            continue  # 已经不在活动仓库里：这正是迁移后的预期状态
        code_ancestor, _ = _git("merge-base", "--is-ancestor", f"refs/tags/{name}",
                                "HEAD")
        assert code_ancestor != 0, (
            f"{name}: 历史 release 不能成为 V3 Final 新历史的祖先")


# --------------------------------------------------------------------------- 6
def test_documents_marking_old_release_refs_stay_honest() -> None:
    payload = _manifest()
    names = {row["name"] for row in payload["historical_releases"]}
    documents = payload["historical_reference_policy"]["checked_documents"]

    for relative in documents:
        path = PROJECT_ROOT / relative
        assert path.is_file(), f"清单里的文档不存在：{relative}"
        text = path.read_text(encoding="utf-8")
        mentioned = sorted(name for name in names if name in text)
        if not mentioned:
            continue
        assert HISTORICAL_MARKER in text, (
            f"{relative} 引用了历史 release {mentioned}，"
            f"但没有标注 {HISTORICAL_MARKER!r}")
