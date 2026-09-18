"""DeliveryService（V4-07 §6、§16、§50、§64–§67、§80–§81）：交付编排。

```text
DeliverySelection → Revision Resolution → DeliverySnapshot → preflight Validation
→ BlueprintCompiler → Exporters(staging) → post-build Validation → publish
→ Manifest(+checksums) → DeliveryResult
```

铁律：

```text
· 0 次 LLM 调用（§49）；不修复 issue（§50）；不写 Blueprint / Canon / StoryState
· snapshot 解析一次，之后所有读取都用钉住的 revision（§23–§24）
· 校验失败在**写文件之前**返回 blocked（§80）
· 构建失败不留伪成功 package（§64–§65）
```
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from novelforge.blueprint import BLUEPRINT_SCHEMA_VERSION, BlueprintRepository

from .compiler import BlueprintCompiler
from .contracts import (
    DELIVERY_SCHEMA_VERSION,
    DeliveryIssue,
    DeliveryPolicy,
    DeliveryRequest,
    DeliveryResult,
    DeliverySelection,
    DeliverySnapshot,
    ExportArtifact,
    utc_now,
)
from .errors import DeliveryExportError, DeliveryFormatError, DeliveryOwnershipError
from .exporters import ExporterRegistry, build_default_registry
from .exporters import package_exporter
from .manifest import build_manifest, sha256_hex
from .selection import RevisionSelector, SelectionOutcome
from .store import DeliveryStore
from .validation import DeliveryValidator


class DeliveryService:
    """一次交付的完整编排（Application 层之下的唯一交付实现）。"""

    def __init__(self, project_root: Path | str, novel_id: str, *,
                 repository: BlueprintRepository | None = None,
                 quality_store: Any = None, editor_store: Any = None,
                 store: DeliveryStore | None = None,
                 registry: ExporterRegistry | None = None,
                 title: str = "") -> None:
        if not str(novel_id or "").strip():
            raise DeliveryOwnershipError("DeliveryService 需要显式 novel_id")
        self.project_root = Path(project_root)
        self.novel_id = str(novel_id)
        self.repository = repository or BlueprintRepository(self.project_root,
                                                            self.novel_id)
        self.quality_store = quality_store
        self.editor_store = editor_store
        self.store = store or DeliveryStore(self.project_root, self.novel_id)
        self.registry = registry or build_default_registry()
        self.title = title
        self.selector = RevisionSelector(self.repository,
                                         quality_store=quality_store,
                                         editor_store=editor_store)
        self.validator = DeliveryValidator(self.repository, quality_store=quality_store)
        self.compiler = BlueprintCompiler(self.repository)

    # ------------------------------------------------------------------ 只读
    def describe(self, selection: DeliverySelection) -> dict[str, Any]:
        """只读：告诉调用方这次会交付什么（不写任何东西）。"""

        outcome = self.selector.select(selection)
        return {"novel_id": self.novel_id, "selection": selection.as_dict(),
                "selection_outcome": outcome.as_dict(),
                "formats": [str(fmt) for fmt in selection.formats],
                "profile": selection.profile,
                "write": False}

    def validate(self, selection: DeliverySelection) -> dict[str, Any]:
        """preflight 校验（不写文件，§80）。"""

        outcome = self.selector.select(selection)
        snapshot = self._build_snapshot(selection, outcome)
        result = self.validator.preflight(selection=selection, outcome=outcome,
                                         snapshot=snapshot)
        return {"snapshot": snapshot.as_dict(), "validation": result.as_dict()}

    def snapshot(self, selection: DeliverySelection, *, persist: bool = True
                 ) -> DeliverySnapshot:
        outcome = self.selector.select(selection)
        snapshot = self._build_snapshot(selection, outcome)
        if persist:
            self.store.save_snapshot(snapshot)
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        return self.store.get_snapshot(snapshot_id)

    def get_manifest(self, snapshot_id: str) -> dict[str, Any]:
        return self.store.get_manifest(snapshot_id)

    def list_snapshots(self) -> list[dict[str, Any]]:
        return self.store.list_snapshots()

    def read_artifact(self, snapshot_id: str, relative_path: str) -> bytes:
        return self.store.read_artifact(snapshot_id, relative_path)

    def stats(self) -> dict[str, Any]:
        return self.store.stats()

    # ------------------------------------------------------- 机器可读视图（只读）
    def machine_representation(self, selection: DeliverySelection) -> dict[str, Any]:
        """只读机器视图（V4-08 §14）：不写 snapshot / 不生成 artifact。

        与 deliver 的区别：这里只回答"当前会交付的内容长什么样"，
        因此 MCP resource / 客户端探测可以直接消费它，而不会产生副作用。
        """

        outcome = self.selector.select(selection)
        snapshot = self._build_snapshot(selection, outcome)
        compiled = self.compiler.compile(snapshot.node_revisions)
        nodes: list[dict[str, Any]] = []
        for node in compiled.nodes:
            state = outcome.quality.get(node.node_id)
            row = node.as_dict(include_internal=True)
            row["review_status"] = self._review_status(node.node_id, node.revision)
            row["quality"] = state.as_dict() if state is not None else {}
            nodes.append(row)
        return {"novel_id": self.novel_id, "selection": selection.as_dict(),
                "snapshot": snapshot.as_dict(),
                "blueprint": {"ordering": list(compiled.ordering),
                              "node_count": compiled.node_count,
                              "node_revisions": {str(key): int(value) for key, value
                                                 in sorted(compiled.node_revisions.items())},
                              "digest": compiled.digest, "nodes": nodes},
                "excluded": [dict(row) for row in outcome.excluded],
                "quality_summary": self.validator._quality_summary(outcome),
                "read_only": True, "artifacts": []}

    def _review_status(self, node_id: str, revision: int) -> str:
        if self.editor_store is None:
            return ""
        row = self.editor_store.review_for(node_id, int(revision))
        return str(row.get("decision") or "")

    # ------------------------------------------------------------------ 交付
    def deliver(self, request: DeliveryRequest) -> DeliveryResult:
        selection = request.selection
        if str(selection.novel_id) != self.novel_id:
            raise DeliveryOwnershipError(
                f"拒绝跨作品交付：{selection.novel_id} != {self.novel_id}",
                details={"novel_id": self.novel_id})
        if request.idempotency_key:
            prior = self.store.find_request(request.idempotency_key)
            if prior:
                return self._replay(prior, request)
        outcome = self.selector.select(selection)
        snapshot = self._build_snapshot(selection, outcome)
        preflight = self.validator.preflight(selection=selection, outcome=outcome,
                                            snapshot=snapshot)
        if not preflight.ok:
            return DeliveryResult(
                request_id=selection.request_id, novel_id=self.novel_id,
                snapshot_id=snapshot.snapshot_id, status="blocked",
                validation=preflight, warnings=preflight.warnings,
                notes=("交付被阻止：未写入任何 artifact（§50 / §80）",))
        if request.dry_run:
            return DeliveryResult(
                request_id=selection.request_id, novel_id=self.novel_id,
                snapshot_id=snapshot.snapshot_id, status="dry_run",
                validation=preflight, warnings=preflight.warnings,
                notes=("dry run：未写 revision、未写交付物",
                       f"formats={[str(fmt) for fmt in selection.formats]}"))
        compiled = self.compiler.compile(snapshot.node_revisions)
        context = self._export_context(selection, snapshot, outcome, compiled)
        artifacts, failures = self._build_artifacts(selection, snapshot, context)
        if failures and not selection.policy.partial_allowed:
            self.store.discard(snapshot.snapshot_id)
            return DeliveryResult(
                request_id=selection.request_id, novel_id=self.novel_id,
                snapshot_id=snapshot.snapshot_id, status="blocked",
                validation=preflight, artifacts=(), warnings=preflight.warnings,
                notes=("exporter 失败：未发布任何 artifact（§64–§65）",
                       *[f"{fmt}: {message}" for fmt, message in failures]))
        manifest = build_manifest(
            snapshot=snapshot, artifacts=artifacts,
            exporters=[self.registry.spec(artifact.format).as_dict()
                       for artifact in artifacts],
            quality_summary=preflight.quality_summary,
            blueprint_schema_version=BLUEPRINT_SCHEMA_VERSION,
            extra={"exporter_failures": [row[0] for row in failures]})
        post = self.validator.post_build(snapshot=snapshot, artifacts=artifacts,
                                        manifest=manifest)
        if not post.ok:
            self.store.discard(snapshot.snapshot_id)
            return DeliveryResult(
                request_id=selection.request_id, novel_id=self.novel_id,
                snapshot_id=snapshot.snapshot_id, status="blocked",
                validation=preflight, post_validation=post, artifacts=(),
                notes=("post-build 校验失败：未发布（§81）", post.blocking_reason))
        secret_hits: list[str] = []
        for artifact in artifacts:
            if str(artifact.format) == "nfpack":
                hits = package_exporter.scan_for_secrets(artifact.content)
                secret_hits.extend(hits)
        if secret_hits:
            self.store.discard(snapshot.snapshot_id)
            return DeliveryResult(
                request_id=selection.request_id, novel_id=self.novel_id,
                snapshot_id=snapshot.snapshot_id, status="blocked",
                validation=preflight, post_validation=post, artifacts=(),
                notes=("package 命中敏感内容扫描：未发布", *sorted(set(secret_hits))))
        self.store.write_staged(snapshot.snapshot_id, "manifest.json",
                               bytes(self._manifest_bytes(manifest)))
        package_path = self.store.publish(snapshot.snapshot_id)
        self.store.save_snapshot(snapshot)
        self.store.save_manifest(manifest)
        if request.idempotency_key:
            self.store.record_request(request.idempotency_key, snapshot.snapshot_id)
        status = "partial" if failures else "delivered"
        return DeliveryResult(
            request_id=selection.request_id, novel_id=self.novel_id,
            snapshot_id=snapshot.snapshot_id, status=status,
            validation=preflight, artifacts=tuple(artifacts),
            manifest=manifest, post_validation=post,
            warnings=preflight.warnings, package_path=str(package_path),
            usage={"llm_calls": 0, "formats": len(artifacts),
                   "bytes": sum(artifact.size for artifact in artifacts)},
            notes=("Delivery 不调用模型、不修复 issue（§49–§50）",
                   f"selected_revisions={len(snapshot.node_revisions)}"))

    # ------------------------------------------------------------------ 内部
    def _build_snapshot(self, selection: DeliverySelection,
                        outcome: SelectionOutcome) -> DeliverySnapshot:
        snapshot_id = f"DS_{selection.digest[:12]}"
        return DeliverySnapshot(
            snapshot_id=snapshot_id, novel_id=self.novel_id,
            node_revisions=dict(outcome.selected),
            selection_mode=selection.selection_mode, profile=selection.profile,
            formats=tuple(str(fmt) for fmt in selection.formats),
            quality_refs=dict(outcome.quality_refs),
            review_refs=dict(outcome.review_refs),
            excluded=tuple(outcome.excluded), policy=selection.policy.as_dict(),
            selection_digest=selection.digest,
            node_types=dict(outcome.node_types),
            created_at=utc_now(), request_id=selection.request_id)

    def _export_context(self, selection: DeliverySelection, snapshot: DeliverySnapshot,
                        outcome: SelectionOutcome, compiled: Any
                        ) -> dict[str, Any]:
        quality_summary = {"by_state": {key: value.state for key, value
                                        in sorted(outcome.quality.items())},
                           "nodes": len(outcome.selected),
                           "policy": selection.policy.as_dict()}
        quality_issues = ([row for row in (self.quality_store.list_issues()
                                           if self.quality_store else [])
                           if any(node_id in (row.get("scope") or {}).get("node_ids", [])
                                  for node_id in snapshot.node_revisions)]
                          if selection.include_quality else [])
        provenance = {}
        if selection.provenance_included:
            provenance = {node.node_id: {"revision": node.revision,
                                         "source_ids": list(node.source_ids),
                                         "generation": dict(node.provenance)}
                          for node in compiled.nodes}
        review = {}
        if selection.review_included:
            review = {"selection_mode": snapshot.selection_mode,
                      "review_refs": dict(sorted(snapshot.review_refs.items())),
                      "decisions": self._review_decisions(snapshot)}
        history = {}
        if selection.history_included:
            history = {"node_revisions": dict(sorted(snapshot.node_revisions.items())),
                       "revisions": self._revision_timeline(snapshot),
                       "operations": (self.editor_store.operations()
                                      if self.editor_store else [])}
        return {"novel_id": self.novel_id, "project_id": self.novel_id,
                "snapshot_id": snapshot.snapshot_id, "title": self.title,
                "selection": selection.as_dict(), "snapshot": snapshot.as_dict(),
                # JSON 内嵌的 manifest 预览（artifact checksum 由交付 manifest.json 记录，§39–§41）
                "manifest": {"manifest_id": f"DM_{snapshot.snapshot_id}",
                             "novel_id": self.novel_id,
                             "project_id": self.novel_id,
                             "snapshot_id": snapshot.snapshot_id,
                             "selection_mode": snapshot.selection_mode,
                             "profile": snapshot.profile,
                             "formats": [str(fmt) for fmt in snapshot.formats],
                             "selected_revisions": {str(key): int(value)
                                                    for key, value in
                                                    sorted(snapshot.node_revisions.items())},
                             "delivery_schema_version": DELIVERY_SCHEMA_VERSION,
                             "blueprint_schema_version": BLUEPRINT_SCHEMA_VERSION,
                             "note": ("artifact checksum / exporter 版本见交付 "
                                      "manifest.json（§39–§41）")},
                "blueprint": compiled.as_dict(include_internal=True),
                "blueprint_schema_version": BLUEPRINT_SCHEMA_VERSION,
                "delivery_schema_version": DELIVERY_SCHEMA_VERSION,
                "quality": quality_summary, "quality_issues": quality_issues,
                "provenance": provenance, "review": review, "history": history,
                "include_node_files": selection.package_includes_node_files,
                "extra_exports": []}

    def _build_artifacts(self, selection: DeliverySelection,
                         snapshot: DeliverySnapshot, context: dict[str, Any]
                         ) -> tuple[list[ExportArtifact], list[tuple[str, str]]]:
        artifacts: list[ExportArtifact] = []
        failures: list[tuple[str, str]] = []
        requested = [str(value) for value in selection.formats]
        # 先做「叶子格式」（json / markdown / docx），再打包 nfpack，
        # 这样 package 内可以携带同一次交付生成的 exports/blueprint.*
        ordered = [fmt for fmt in requested if fmt != "nfpack"] + \
                  [fmt for fmt in requested if fmt == "nfpack"]
        for fmt in ordered:
            try:
                spec, fn = self.registry.get(fmt)
            except DeliveryFormatError as exc:
                failures.append((fmt, exc.message))
                continue
            if selection.profile not in spec.profiles_supported:
                failures.append((fmt, f"exporter 不支持 profile {selection.profile}"))
                continue
            payload_ctx = self._context_for_format(fmt, context, selection)
            if fmt == "nfpack":
                payload_ctx = {**payload_ctx,
                               "extra_exports": [
                                   {"path": f"exports/{row.filename}",
                                    "data": row.content}
                                   for row in artifacts]}
            try:
                payload = bytes(fn(payload_ctx))
            except Exception as exc:  # noqa: BLE001 - 失败必须被显式报告（§65）
                failures.append((fmt, f"{type(exc).__name__}: {exc}"))
                continue
            relative = (f"package/novelforge-package.{spec.extension}"
                        if fmt == "nfpack" else f"exports/blueprint.{spec.extension}")
            self.store.write_staged(snapshot.snapshot_id, relative, payload)
            artifacts.append(ExportArtifact(
                format=fmt, filename=f"blueprint.{spec.extension}",
                relative_path=relative, mime_type=spec.mime_type,
                size=len(payload), checksum=sha256_hex(payload),
                exporter_id=spec.exporter_id, exporter_version=spec.version,
                content=payload, text=bool(spec.text)))
        return artifacts, failures

    @staticmethod
    def _context_for_format(fmt: str, context: Mapping[str, Any],
                            selection: DeliverySelection) -> dict[str, Any]:
        """按格式裁剪 context（reader profile 不携带内部 metadata，§30）。"""

        payload = dict(context)
        if fmt in ("markdown", "docx") and selection.profile == "reader":
            payload.pop("provenance", None)
            payload.pop("history", None)
            payload.pop("review", None)
        if fmt in ("markdown", "docx") and not selection.provenance_included:
            payload.pop("provenance", None)
        if fmt in ("markdown", "docx") and not selection.history_included:
            payload.pop("history", None)
        if fmt in ("markdown", "docx") and not selection.review_included:
            payload.pop("review", None)
        if fmt != "nfpack":
            payload.pop("include_node_files", None)
            payload.pop("quality_issues", None)
        if fmt == "json" and not selection.include_quality:
            payload.pop("quality", None)
            payload.pop("quality_issues", None)
        return payload

    def _review_decisions(self, snapshot: DeliverySnapshot) -> list[dict[str, Any]]:
        if self.editor_store is None:
            return []
        rows: list[dict[str, Any]] = []
        for node_id, revision in sorted(snapshot.node_revisions.items()):
            row = self.editor_store.review_for(node_id, int(revision))
            if row:
                rows.append(row)
        return rows

    def _revision_timeline(self, snapshot: DeliverySnapshot) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for node_id, revision in sorted(snapshot.node_revisions.items()):
            stored = self.repository.get_revision(node_id, int(revision))
            if stored is None:
                continue
            rows.append({"node_id": node_id, "revision": int(revision),
                         "parent_revision": int(stored.parent_revision),
                         "status": str(stored.status),
                         "quality_status": str(stored.quality_status),
                         "created_at": str(stored.created_at),
                         "updated_at": str(stored.updated_at),
                         "generation_contract": str(stored.generation_contract),
                         "source_ids": list(stored.source_ids)})
        return rows

    @staticmethod
    def _manifest_bytes(manifest: Any) -> bytes:
        import json

        return (json.dumps(manifest.as_dict(), ensure_ascii=False, indent=1,
                           sort_keys=True) + "\n").encode("utf-8")

    def _replay(self, prior: Mapping[str, Any], request: DeliveryRequest
                ) -> DeliveryResult:
        snapshot_id = str(prior.get("snapshot_id") or "")
        snapshot_row = self.store.get_snapshot(snapshot_id)
        manifest_row = self.store.get_manifest(snapshot_id)
        if not snapshot_row or not manifest_row:
            raise DeliveryExportError(
                "幂等记录指向不存在的交付物",
                details={"snapshot_id": snapshot_id,
                         "idempotency_key": request.idempotency_key})
        selection = request.selection
        from .contracts import DeliveryValidationResult

        validation = DeliveryValidationResult(
            novel_id=self.novel_id, phase="preflight", ok=True,
            selected_revisions={str(key): int(value) for key, value in
                                (snapshot_row.get("node_revisions") or {}).items()},
            quality_summary=dict(manifest_row.get("quality_summary") or {}))
        artifacts = tuple(
            ExportArtifact(format=str(row.get("format")),
                           filename=str(row.get("filename") or ""),
                           relative_path=str(row.get("path") or ""),
                           mime_type=str(row.get("mime_type") or ""),
                           size=int(row.get("size") or 0),
                           checksum=str(row.get("checksum") or ""),
                           exporter_id=str(row.get("exporter_id") or ""),
                           exporter_version=int(row.get("exporter_version") or 1),
                           content=b"", text=True)
            for row in (manifest_row.get("artifacts") or []))
        return DeliveryResult(
            request_id=selection.request_id, novel_id=self.novel_id,
            snapshot_id=snapshot_id, status="delivered", validation=validation,
            artifacts=artifacts, idempotent=True,
            package_path=str(self.store.package_dir(snapshot_id)),
            notes=("idempotent replay：该 idempotency_key 已交付过，未重新生成",))

def delivery_service(project_root: Path | str, novel_id: str, **kwargs: Any
                     ) -> DeliveryService:
    return DeliveryService(project_root, novel_id, **kwargs)


__all__ = ["DeliveryService", "delivery_service"]
