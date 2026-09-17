"""C10：Canon 只读检查 API + rebuild / validate-outline（遵守既有 /api 风格，不开放 happened 编辑）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query
from pydantic import Field

from novelforge.models import StrictModel
from novelforge.persistence.paths import canon_db_path as _canon_db_path
from novelforge.story_engine.profile import DEFAULT_NOVEL_ID
from novelforge.story_engine.canon.bootstrap import CanonBootstrap
from novelforge.story_engine.canon.chapters import ChapterLineageStore
from novelforge.story_engine.canon.gate import SchemaGateError, validate_chapter_plan
from novelforge.story_engine.canon.graph import CanonGraph, CanonGraphValidator
from novelforge.story_engine.canon.repository import CanonRepository
from novelforge.story_engine.canon.semantic import EventSemanticSignature, LocalSemanticIndex
from novelforge.story_engine.canon.validator import SourceReferenceValidator
from novelforge.story_engine.canon.models import CanonSourceRef

# V4-01：默认作品不再是废弃的 wasteland_001。这里复用产品通用默认 id
# （story_engine.profile.DEFAULT_NOVEL_ID = "novel_project"）；
# 客户端（UI / MCP）必须显式传 novel_id，服务端不做磁盘推断。


class RebuildRequest(StrictModel):
    state: dict[str, Any] = Field(default_factory=dict)
    content_pack: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)


class ValidateOutlineRequest(StrictModel):
    chapters: list[dict[str, Any]] = Field(default_factory=list)
    temporal_cutoff: int | None = Field(default=None, ge=0)


def canon_db_path(project_root: Path, novel_id: str) -> Path:
    """兼容包装：唯一实现已迁到 `persistence.paths.canon_db_path`（V4-01）。"""

    return _canon_db_path(project_root, novel_id)


def install_canon_api(app: FastAPI, project_root: Path) -> None:
    # 复用既有产品命名空间（封版约束：只暴露 /api/story-builder/* 与 /api/health）
    router = APIRouter(prefix="/api/story-builder/canon", tags=["canon"])

    def repo_for(novel_id: str) -> CanonRepository:
        return CanonRepository(canon_db_path(project_root, novel_id))

    @router.get("/facts")
    def list_facts(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
                   status: str = Query(default="", max_length=32),
                   limit: int = Query(default=50, ge=1, le=500),
                   offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
        repository = repo_for(novel_id)
        try:
            rows = [f.model_dump(mode="json") for f in repository.facts(novel_id, status=status)]
            return {"novel_id": novel_id, "total": len(rows),
                    "items": rows[offset:offset + limit]}
        finally:
            repository.close()

    @router.get("/events")
    def list_events(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
                    role: str = Query(default="", max_length=32),
                    limit: int = Query(default=50, ge=1, le=500),
                    offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
        repository = repo_for(novel_id)
        try:
            rows = [e.model_dump(mode="json") for e in repository.events(novel_id, role=role)]
            return {"novel_id": novel_id, "total": len(rows),
                    "items": rows[offset:offset + limit]}
        finally:
            repository.close()

    @router.get("/entities")
    def list_entities(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
                      limit: int = Query(default=50, ge=1, le=500),
                      offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
        repository = repo_for(novel_id)
        try:
            rows = [e.model_dump(mode="json") for e in repository.entities(novel_id)]
            return {"novel_id": novel_id, "total": len(rows),
                    "items": rows[offset:offset + limit]}
        finally:
            repository.close()

    @router.get("/knowledge")
    def list_knowledge(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
                       holder_id: str = Query(default="", max_length=128),
                       limit: int = Query(default=50, ge=1, le=500),
                       offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
        repository = repo_for(novel_id)
        try:
            rows = [k.model_dump(mode="json") for k in repository.knowledge(novel_id)
                    if not holder_id or k.holder_id == holder_id]
            return {"novel_id": novel_id, "total": len(rows),
                    "items": rows[offset:offset + limit]}
        finally:
            repository.close()

    @router.get("/foreshadows")
    def list_foreshadows(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
        limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        repository = repo_for(novel_id)
        try:
            rows = [f.model_dump(mode="json") for f in repository.foreshadows(novel_id)]
            return {"novel_id": novel_id, "total": len(rows), "items": rows[:limit]}
        finally:
            repository.close()

    @router.get("/graph")
    def graph_summary(novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96),
                      limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
        repository = repo_for(novel_id)
        try:
            graph = CanonGraph.from_repository(repository, novel_id)
            edges = [{"from": u, "to": v, "relation": key}
                     for u, v, key in list(graph.graph.edges(keys=True))[:limit]]
            return {"novel_id": novel_id,
                    "nodes": list(graph.graph.nodes)[:limit], "node_count": graph.graph.number_of_nodes(),
                    "edges": edges, "edge_count": graph.graph.number_of_edges()}
        finally:
            repository.close()

    @router.get("/validate")
    def validate_canon(
        novel_id: str = Query(default=DEFAULT_NOVEL_ID, min_length=3, max_length=96)) -> dict[str, Any]:
        repository = repo_for(novel_id)
        try:
            graph = CanonGraph.from_repository(repository, novel_id)
            findings = CanonGraphValidator(graph).run()
            refs = SourceReferenceValidator(repository).promotion_conflicts(novel_id)
            return {"novel_id": novel_id, "ok": not findings and not refs,
                    "findings": findings, "promotion_conflicts": [f.model_dump() for f in refs],
                    "schema": repository.schema_summary()}
        finally:
            repository.close()

    @router.post("/rebuild")
    def rebuild_canon(novel_id: str, body: RebuildRequest) -> dict[str, Any]:
        repository = repo_for(novel_id)
        try:
            result = CanonBootstrap(repository).rebuild(
                novel_id, state=body.state or None, content_pack=body.content_pack or None,
                profile=body.profile or None)
            return result.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 - 失败保留原 DB
            raise HTTPException(status_code=422, detail={"code": "REBUILD_FAILED",
                                                         "message": str(exc)[:200]}) from exc
        finally:
            repository.close()

    @router.post("/validate-outline")
    def validate_outline(novel_id: str, body: ValidateOutlineRequest) -> dict[str, Any]:
        repository = repo_for(novel_id)
        try:
            findings: list[dict[str, Any]] = []
            planned = []
            for index, raw in enumerate(body.chapters, start=1):
                try:
                    plan = validate_chapter_plan(raw)
                    planned.append(plan)
                except SchemaGateError as exc:
                    findings.append({"code": "CHAPTER_SCHEMA_INVALID", "chapter": index,
                                     "issues": exc.issues[:5]})
            validator = SourceReferenceValidator(repository)
            for plan in planned:
                report = validator.validate_refs(
                    novel_id, refs=list(plan.canon_source_refs),
                    claimed_fact_ids=plan.canon_fact_ids, temporal_cutoff=body.temporal_cutoff)
                findings.extend(f.model_dump() for f in report.findings)
            index = LocalSemanticIndex()
            for plan in planned:
                index.index_event(EventSemanticSignature(
                    event_id=plan.chapter_uuid, semantic_summary=plan.goal,
                    subjects=list(plan.participants), location=plan.location))
            duplicates = []
            for plan in planned:
                signature = EventSemanticSignature(event_id=plan.chapter_uuid,
                                                   semantic_summary=plan.goal,
                                                   subjects=list(plan.participants),
                                                   location=plan.location)
                duplicates.extend({"chapter": plan.chapter_uuid,
                                   "candidates": [c.model_dump() for c in
                                                  index.candidates(signature, top_k=3)]})
            return {"novel_id": novel_id, "ok": not findings, "findings": findings,
                    "duplicate_candidates": [d for d in duplicates if d["candidates"]]}
        finally:
            repository.close()

    app.include_router(router)
