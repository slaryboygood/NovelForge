# Source Map — NovelForge V4.0.1 Skill Library

> 每个 skill 都必须可追溯到 contract / source owner / 接口 / 测试。
> `tests/v4/skills/test_source_map.py` 会机械校验本文件里的路径与 interface 引用真实存在。
> REST 前缀省略：`/studio/*` = `/api/story-builder/studio/*`。`N/A` = 当前无该接口（不是疏漏，见 GAP 文档）。

| Skill ID | Contract | Source Owner | REST | MCP | Tests |
| --- | --- | --- | --- | --- | --- |
| `project.create-novel` | `docs/v4/V4_MODULE_BOUNDARIES.md` | `src/novelforge/application/services/project.py` | `POST /novels` | N/A | `tests/acceptance/test_final_integration.py` |
| `project.inspect-novels` | 同上 | `src/novelforge/application/services/project.py` | `GET /novels`, `GET /novels/{novel_id}` | `novelforge://novels/{novel_id}` | `tests/acceptance/test_final_integration.py` |
| `project.rename-novel` | 同上 | `src/novelforge/application/services/novel_admin.py` | `PATCH /novels/{novel_id}` | N/A | `tests/acceptance/test_final_release.py` |
| `project.archive-novel` | 同上 | `src/novelforge/application/services/novel_admin.py` | `DELETE /novels/{novel_id}` | N/A | `tests/acceptance/test_final_release.py` |
| `studio.open-story-studio` | `docs/v4/V4_UI_CONTRACT.md` | `scripts/start_novelforge_ui.py` | `GET /` | N/A | `tests/browser_v4_studio_golden.cjs` |
| `studio.navigate-studio-workspace` | `docs/v4/V4_UI_CONTRACT.md` | `ui/src/studio/nav.ts` | N/A | N/A | `ui/src/studio/nav.test.ts` |
| `studio.inspect-overview` | `docs/v4/V4_UI_CONTRACT.md` | `src/novelforge/api/studio_routes.py` | `GET /studio/overview` | `novelforge://novels/{novel_id}` | `tests/studio/test_studio_api.py` |
| `studio.handle-legacy-url` | `docs/v4/V4_POST_RELEASE_CLEANUP_REPORT.md` | `ui/src/App.tsx` | `GET /` | N/A | `tests/browser_v4_legacy_entry.cjs` |
| `blueprint.inspect-blueprint` | `docs/v4/V4_BLUEPRINT_CONTRACT.md` | `src/novelforge/blueprint/repository.py` | `GET /studio/blueprint` | `.../blueprint` | `tests/studio/test_studio_api.py` |
| `blueprint.inspect-node` | `docs/v4/V4_EDITOR_CONTRACT.md` | `src/novelforge/application/services/editor.py` | `GET /editor/nodes/{node_id}` | `.../blueprint/nodes/{node_id}` | `tests/editor/test_manual_edit.py` |
| `blueprint.inspect-revisions` | `docs/v4/V4_EDITOR_CONTRACT.md` | `src/novelforge/editor/history.py` | `GET /editor/nodes/{node_id}/revisions` | `.../revisions/{revision}` | `tests/editor/test_revision_history.py` |
| `blueprint.inspect-scene-cards` | `docs/v4/V4_BLUEPRINT_CONTRACT.md` | `src/novelforge/blueprint/contracts.py` | `GET /studio/blueprint?node_type=scene` | `.../scenes` | `tests/generation/test_generation_pipeline.py` |
| `blueprint.understand-blueprint-model` | `docs/v4/V4_BLUEPRINT_CONTRACT.md` | `src/novelforge/blueprint/contracts.py` | N/A | N/A | `tests/generation/test_blueprint_contracts.py` |
| `generation.generate-premise` | `docs/v4/V4_BLUEPRINT_CONTRACT.md` | `src/novelforge/generation/tasks/premise.py` | `POST /studio/generate` | `generate_premise` | `tests/generation/test_generation_service.py` |
| `generation.generate-theme` | 同上 | `src/novelforge/generation/tasks/premise.py` | `POST /studio/generate` | `generate_theme` | `tests/generation/test_generation_pipeline.py` |
| `generation.generate-world` | 同上 | `src/novelforge/generation/tasks/world.py` | `POST /studio/generate` | `generate_world` | `tests/generation/test_generation_service.py` |
| `generation.generate-character` | 同上 | `src/novelforge/generation/tasks/characters.py` | `POST /studio/generate` | `generate_character` | `tests/generation/test_generation_validation.py` |
| `generation.generate-character-arc` | 同上 | `src/novelforge/generation/tasks/characters.py` | `POST /studio/generate` | `generate_character_arc` | `tests/generation/test_generation_validation.py` |
| `generation.generate-story-arc` | 同上 | `src/novelforge/generation/tasks/story.py` | `POST /studio/generate` | `generate_story_arc` | `tests/generation/test_generation_pipeline.py` |
| `generation.generate-structural-unit` | 同上 | `src/novelforge/generation/tasks/story.py` | `POST /studio/generate` | `generate_structural_unit` | `tests/generation/test_generation_pipeline.py` |
| `generation.generate-chapter-plan` | 同上 | `src/novelforge/generation/tasks/chapter.py` | `POST /studio/generate` | `generate_chapter_plan` | `tests/generation/test_generation_pipeline.py` |
| `generation.generate-scene-plan` | 同上 | `src/novelforge/generation/tasks/scene.py` | `POST /studio/generate` | `generate_scene_plan` | `tests/generation/test_generation_service.py` |
| `memory.inspect-derived-memory` | `docs/v4/V4_MEMORY_ARCHITECTURE.md` | `src/novelforge/memory/service.py` | N/A | N/A | `tests/memory/test_retrieval_contract.py` |
| `memory.build-generation-context` | `docs/v4/V4_MEMORY_ARCHITECTURE.md` | `src/novelforge/memory/context/builder.py` | N/A | N/A | `tests/memory/test_context_builder.py` |
| `memory.understand-truth-precedence` | `docs/v4/adr/ADR-014-memory-is-derived-canon-remains-authoritative.md` | `src/novelforge/memory/__init__.py` | N/A | N/A | `tests/v4/isolation/test_memory_ownership.py` |
| `quality.evaluate-blueprint` | `docs/v4/V4_QUALITY_CONTRACT.md` | `src/novelforge/application/services/review.py` | `POST /studio/quality/evaluate` | `evaluate_blueprint` | `tests/quality/test_quality_service.py` |
| `quality.inspect-quality-report` | 同上 | `src/novelforge/application/services/review.py` | `GET /studio/quality` | `.../quality` | `tests/studio/test_studio_api.py` |
| `quality.list-quality-issues` | 同上 | `src/novelforge/quality/store.py` | `GET /studio/quality` | `.../quality/issues` | `tests/quality/test_quality_contracts.py` |
| `quality.understand-quality-gates` | `docs/v4/V4_QUALITY_CONTRACT.md` | `src/novelforge/quality/contracts.py` | N/A | N/A | `tests/quality/test_quality_registry.py` |
| `repair.plan-repair` | `docs/v4/V4_REPAIR_CONTRACT.md` | `src/novelforge/quality/repair/planner.py` | `POST /studio/quality/repair` | `plan_repair` | `tests/quality/repair/test_planner.py` |
| `repair.apply-repair` | 同上 | `src/novelforge/quality/repair/executor.py` | `POST /studio/quality/repair` | `repair_issue` | `tests/quality/repair/test_executor.py` |
| `repair.verify-repair` | 同上 | `src/novelforge/quality/repair/verifier.py` | `POST /studio/quality/verify` | `verify_repair` | `tests/quality/repair/test_verifier.py` |
| `repair.understand-repair-contract` | `docs/v4/V4_REPAIR_CONTRACT.md` | `src/novelforge/quality/repair/contracts.py` | N/A | N/A | `tests/test_acceptance_repair_regressions.py` |
| `editor.patch-node` | `docs/v4/V4_EDITOR_CONTRACT.md` | `src/novelforge/editor/patch.py` | `PATCH /editor/nodes/{node_id}` | `patch_blueprint_node` | `tests/editor/test_manual_edit.py` |
| `editor.rewrite-node` | 同上 | `src/novelforge/generation/rewrite.py` | `POST /editor/nodes/{node_id}/rewrite` | `rewrite_blueprint_node` | `tests/editor/test_ai_rewrite.py` |
| `editor.accept-revision` | 同上 | `src/novelforge/blueprint/lifecycle.py` | `POST /editor/nodes/{node_id}/accept` | `accept_revision` | `tests/editor/test_accept_reject.py` |
| `editor.reject-revision` | 同上 | `src/novelforge/application/services/editor.py` | `POST /editor/nodes/{node_id}/reject` | `reject_revision` | `tests/editor/test_accept_reject.py` |
| `editor.restore-revision` | 同上 | `src/novelforge/editor/history.py` | `POST /editor/nodes/{node_id}/restore` | `restore_revision` | `tests/editor/test_restore.py` |
| `editor.diff-revisions` | 同上 | `src/novelforge/editor/diff.py` | `GET /editor/nodes/{node_id}/diff` | `diff_revisions` | `tests/editor/test_diff.py` |
| `delivery.validate-delivery` | `docs/v4/V4_DELIVERY_CONTRACT.md` | `src/novelforge/delivery/validation.py` | `POST /delivery` | `validate_delivery` | `tests/delivery/test_validation.py` |
| `delivery.create-delivery-snapshot` | 同上 | `src/novelforge/delivery/store.py` | `POST /delivery` | `create_delivery_snapshot` | `tests/delivery/test_delivery_service.py` |
| `delivery.deliver-blueprint` | 同上 | `src/novelforge/delivery/service.py` | `POST /delivery` | `deliver_blueprint` | `tests/delivery/test_exporters.py` |
| `delivery.inspect-delivery-manifest` | 同上 | `src/novelforge/delivery/manifest.py` | `GET /delivery/{snapshot_id}/manifest` | `.../delivery/{snapshot_id}/manifest` | `tests/delivery/test_delivery_contracts.py` |
| `delivery.download-delivery-artifact` | 同上 | `src/novelforge/application/services/export.py` | `GET /delivery/{snapshot_id}/artifacts/{artifact_path}` | `.../artifacts/{artifact_path}` | `tests/delivery/test_export_facade_and_api.py` |
| `delivery.list-delivery-snapshots` | 同上 | `src/novelforge/application/services/export.py` | `GET /delivery/snapshots` | `.../delivery` | `tests/delivery/test_delivery_service.py` |
| `canon.inspect-canon-truth` | `docs/v4/V4_MODULE_BOUNDARIES.md` | `src/novelforge/story_engine/canon/repository.py` | `GET /canon/facts`, `/events`, `/entities`, `/knowledge`, `/foreshadows` | N/A | `tests/test_canon_repository.py` |
| `canon.inspect-canon-graph` | 同上 | `src/novelforge/story_engine/canon/graph.py` | `GET /canon/graph` | N/A | `tests/test_canon_graph.py` |
| `canon.validate-canon-integrity` | 同上 | `src/novelforge/story_engine/canon/validator.py` | `GET /canon/validate` | N/A | `tests/test_source_reference_validator.py` |
| `canon.validate-planning-against-canon` | 同上 | `src/novelforge/story_engine/canon/gate.py` | `POST /canon/validate-outline` | N/A | `tests/test_canon_outline_integration.py` |
| `canon.rebuild-canon` | 同上 | `src/novelforge/story_engine/canon/bootstrap.py` | `POST /canon/rebuild` | N/A | `tests/test_canon_bootstrap_api.py` |
| `story-state.understand-story-state-boundary` | `docs/DATA_MODEL.md` | `src/novelforge/story_engine/state.py` | N/A | N/A | `tests/v4/isolation/test_memory_ownership.py` |
| `story-state.inspect-story-state` | 同上 | `src/novelforge/story_engine/context.py` | N/A | N/A | `tests/test_canon_context.py` |
| `plugins.inspect-plugins` | `docs/v4/V4_PLUGIN_CONTRACT.md` | `src/novelforge/application/services/plugins.py` | `GET /studio/plugins` | N/A | `tests/plugins/test_plugin_contracts.py` |
| `plugins.inspect-plugin-contributions` | 同上 | `src/novelforge/plugins/adapters/exporter.py` | N/A | N/A | `tests/plugins/test_plugin_registration.py` |
| `plugins.approve-plugin` | 同上 | `src/novelforge/plugins/permissions.py` | N/A | N/A | `tests/plugins/test_plugin_permissions.py` |
| `plugins.enable-plugin` | 同上 | `src/novelforge/plugins/host.py` | N/A | N/A | `tests/plugins/test_plugin_lifecycle.py` |
| `plugins.disable-plugin` | 同上 | `src/novelforge/plugins/registry.py` | N/A | N/A | `tests/plugins/test_plugin_state.py` |
| `agent.plan-agent-goal` | `docs/v4/V4_AGENT_CONTRACT.md` | `src/novelforge/agent/planner.py` | `POST /agent/plan` | N/A | `tests/agent/test_agent_planner.py` |
| `agent.start-agent-session` | 同上 | `src/novelforge/agent/executor.py` | `POST /agent/start` | N/A | `tests/agent/test_agent_execution.py` |
| `agent.inspect-agent-session` | 同上 | `src/novelforge/agent/audit.py` | `GET /agent/sessions`, `GET /agent/{session_id}` | N/A | `tests/agent/test_agent_resume_budget.py` |
| `agent.approve-agent-run` | 同上 | `src/novelforge/agent/policy.py` | `POST /agent/{session_id}/approve` | N/A | `tests/agent/test_agent_approval.py` |
| `agent.resume-agent-session` | 同上 | `src/novelforge/agent/checkpoint.py` | `POST /agent/{session_id}/resume` | N/A | `tests/agent/test_agent_resume_budget.py` |
| `agent.cancel-agent-session` | 同上 | `src/novelforge/application/services/agent.py` | `POST /agent/{session_id}/cancel` | N/A | `tests/agent/test_agent_execution.py` |
| `mcp.start-mcp-server` | `docs/v4/V4_MCP_CONTRACT.md` | `src/novelforge/interfaces/mcp/server.py` | N/A | server `novelforge` | `tests/mcp/test_mcp_server.py` |
| `mcp.discover-mcp-surface` | 同上 | `src/novelforge/interfaces/mcp/registry.py` | N/A | 23 tools / 13 resources | `tests/mcp/test_mcp_tools.py` |
| `mcp.read-mcp-resource` | 同上 | `src/novelforge/interfaces/mcp/resources/__init__.py` | N/A | 13 resources | `tests/mcp/test_mcp_resources.py` |
| `mcp.call-mcp-tool` | 同上 | `src/novelforge/interfaces/mcp/tools/__init__.py` | N/A | 23 tools | `tests/mcp/test_mcp_contracts.py` |
| `mcp.understand-mcp-boundary` | `docs/v4/adr/ADR-027-mcp-is-an-interface-adapter-not-a-business-layer.md` | `src/novelforge/interfaces/mcp/__init__.py` | N/A | N/A | `tests/v4/isolation/test_mcp_boundaries.py` |
| `ai.configure-llm-provider` | `docs/v4/V4_LLM_CONTRACT.md` | `src/novelforge/ai/config.py` | N/A | N/A | `tests/ai/test_config.py` |
| `ai.inspect-llm-provider-config` | 同上 | `src/novelforge/ai/config.py` | N/A | N/A | `tests/ai/test_provider_contract.py` |
| `ai.run-without-provider` | `docs/v4/adr/ADR-012-unified-llm-gateway.md` | `src/novelforge/ai/gateway.py` | `POST /studio/generate` | `generate_*` | `tests/ai/test_gateway.py` |
| `ai.understand-llm-gateway-boundary` | `docs/v4/V4_LLM_CONTRACT.md` | `src/novelforge/ai/gateway.py` | N/A | N/A | `tests/v4/isolation/test_generation_boundaries.py` |
| `workflows.create-new-story-blueprint` | 组合（见各步） | `skills/novelforge-v4.0.1/workflows/create-new-story-blueprint/SKILL.md` | 见各步 | 见各步 | `tests/v4/skills/test_module_boundaries.py` |
| `workflows.review-and-repair-blueprint` | 组合 | `skills/novelforge-v4.0.1/workflows/review-and-repair-blueprint/SKILL.md` | 见各步 | 见各步 | `tests/v4/skills/test_module_boundaries.py` |
| `workflows.prepare-final-delivery` | 组合 | `skills/novelforge-v4.0.1/workflows/prepare-final-delivery/SKILL.md` | 见各步 | 见各步 | `tests/v4/skills/test_module_boundaries.py` |
| `workflows.use-novelforge-through-mcp` | 组合 | `skills/novelforge-v4.0.1/workflows/use-novelforge-through-mcp/SKILL.md` | 见各步 | 见各步 | `tests/v4/skills/test_module_boundaries.py` |
| `workflows.operate-with-agent` | 组合 | `skills/novelforge-v4.0.1/workflows/operate-with-agent/SKILL.md` | 见各步 | 见各步 | `tests/v4/skills/test_module_boundaries.py` |

## 说明

```text
· Skill ID 在表里省略 `novelforge-v4.0.1.` 前缀（首列完整写法见 SKILL_CATALOG.md）
· 同一 skill 可能引用多个 REST / MCP 条目；这里列出该 skill 的主要接口
· `N/A` 表示当前没有该接口（GAP 文档记录了原因与建议处置）
```
