"""Legacy LLM 调用迁移测试（V4-02 §24）。"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fake_provider import build_harness

from novelforge.ai import LLMError

SPEC_LLM = (Path(__file__).resolve().parents[2] / "src" / "novelforge"
            / "story_engine" / "spec" / "llm.py")

SPEC_PAYLOAD = {"fields": [{"field": "genre", "value": "工程", "rationale": "题材方向",
                            "confidence": 0.6}]}


def _spec_and_gaps():
    from novelforge.story_engine.spec import NovelSpec, find_spec_gaps

    spec = NovelSpec(spec_id="SPEC_LEGACY_1", novel_id="novel_legacy_1",
                     logline="一个只属于测试的创意：把断掉的桥重新接上。",
                     genre="", themes=["修补意味着承担"], tone="克制",
                     pace_strategy="压力前置")
    return spec, find_spec_gaps(spec)


def _http_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in {"urllib", "httpx", "requests",
                                                "openai", "anthropic"}:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in {"urllib", "httpx", "requests",
                                                     "openai", "anthropic"}:
                found.append(node.module or "")
    return found


def test_spec_llm_has_no_http_client_and_no_hardcoded_model() -> None:
    assert _http_imports(SPEC_LLM) == [], (
        "legacy 适配器不得自己发 HTTP（必须经 novelforge.ai）")
    text = SPEC_LLM.read_text(encoding="utf-8")
    assert "DEFAULT_MODEL =" not in text
    assert "DEFAULT_ENDPOINT =" not in text
    assert "api.deepseek.com" not in text


def test_spec_llm_routes_through_injected_gateway() -> None:
    from novelforge.story_engine.spec import LLMSpecProposalProvider

    harness = build_harness(script=[json.dumps(SPEC_PAYLOAD)], provider_id="fake")
    provider = LLMSpecProposalProvider(gateway=harness.gateway, model="fake-model",
                                       api_key="sk-ignored")
    spec, gaps = _spec_and_gaps()
    proposal = provider.propose(spec, gaps)

    assert proposal.provider == "llm"
    assert proposal.field("genre").value == "工程"
    assert harness.provider.call_count == 1, "必须经 Gateway 调用 provider"
    trace = harness.trace.recent(1)
    assert trace and trace[0]["operation"] == "spec_proposal"
    assert trace[0]["status"] == "ok"


def test_spec_llm_keeps_schema_retry_semantics(monkeypatch) -> None:
    from novelforge.story_engine.spec import LLMSpecProposalProvider
    import novelforge.story_engine.spec.llm as spec_llm

    monkeypatch.setattr(spec_llm.time, "sleep", lambda _seconds: None)
    harness = build_harness(script=["这不是 JSON", json.dumps(SPEC_PAYLOAD)],
                            provider_id="fake")
    provider = LLMSpecProposalProvider(gateway=harness.gateway, model="fake-model",
                                       api_key="sk-ignored", max_attempts=3)
    proposal = provider.propose(*_spec_and_gaps())
    assert proposal.field("genre").value == "工程"
    assert harness.provider.call_count == 2, "schema 失败必须重试（既有语义）"


def test_spec_llm_missing_key_reports_legacy_error_code() -> None:
    from novelforge.story_engine.spec import LLMSpecProposalProvider, SpecProposalError

    provider = LLMSpecProposalProvider(api_key="", model="fake-model",
                                       endpoint="http://localhost:9/v1")
    with pytest.raises(SpecProposalError) as exc:
        provider.propose(*_spec_and_gaps())
    assert exc.value.code == "BLOCKED_REAL_LLM_PROPOSER_UNAVAILABLE"


def test_spec_llm_missing_model_or_endpoint_reports_configuration() -> None:
    from novelforge.story_engine.spec import LLMSpecProposalProvider, SpecProposalError

    with pytest.raises(SpecProposalError) as exc:
        LLMSpecProposalProvider(api_key="sk-x", model="",
                                endpoint="http://localhost:9/v1").propose(
            *_spec_and_gaps())
    assert exc.value.code == "BLOCKED_REAL_LLM_PROPOSER_UNAVAILABLE"
    assert "NOVELFORGE_SPEC_MODEL" in exc.value.message


def test_spec_llm_maps_gateway_errors_to_legacy_codes() -> None:
    from novelforge.ai import ProviderUnavailableError
    from novelforge.story_engine.spec import LLMSpecProposalProvider, SpecProposalError

    harness = build_harness(script=[ProviderUnavailableError("boom")],
                            provider_id="fake", max_attempts=1)
    provider = LLMSpecProposalProvider(gateway=harness.gateway, model="fake-model",
                                       api_key="sk-x", max_attempts=1)
    with pytest.raises(SpecProposalError) as exc:
        provider.propose(*_spec_and_gaps())
    assert exc.value.code == "SPEC_PROPOSAL_HTTP_FAILURE"


def test_spec_llm_empty_response_is_reported() -> None:
    from novelforge.story_engine.spec import LLMSpecProposalProvider, SpecProposalError

    harness = build_harness(script=["   "], provider_id="fake", max_attempts=1)
    provider = LLMSpecProposalProvider(gateway=harness.gateway, model="fake-model",
                                       api_key="sk-x", max_attempts=1)
    with pytest.raises(SpecProposalError) as exc:
        provider.propose(*_spec_and_gaps())
    assert exc.value.code in ("SPEC_PROPOSAL_EMPTY_RESPONSE",
                              "SPEC_PROPOSAL_JSON_INVALID")
    assert LLMError  # 保持 import 使用（契约存在于 ai）


# ---------------------------------------------------------------- planning providers
PLANNING_LLM_FILES = (
    Path("src/novelforge/story_engine/planning/plot_synthesis.py"),
    Path("src/novelforge/story_engine/planning/route_candidates.py"),
)


@pytest.mark.parametrize("relative", PLANNING_LLM_FILES)
def test_planning_llm_providers_have_no_http_client_or_hardcoded_endpoint(relative) -> None:
    path = Path(__file__).resolve().parents[2] / relative
    text = path.read_text(encoding="utf-8")
    assert _http_imports(path) == [], (
        f"{relative} 不得自己发 HTTP（必须经 novelforge.ai）")
    assert "api.deepseek.com" not in text
    assert 'model: str = "deepseek-chat"' not in text


def test_plot_provider_reports_legacy_code_when_unconfigured() -> None:
    from novelforge.story_engine.planning.plot_synthesis import (
        LLMPlotCandidateProvider,
        PlotProposalError,
    )

    provider = LLMPlotCandidateProvider(api_key="", model="",
                                        base_url="http://localhost:9/v1")
    with pytest.raises(PlotProposalError) as exc:
        provider.propose({"revision": "rev_1"}, source_revision="rev_1")
    assert exc.value.code == "BLOCKED_REAL_LLM_PROPOSER_UNAVAILABLE"


def test_route_provider_reports_legacy_code_when_unconfigured() -> None:
    from novelforge.story_engine.planning.route_candidates import (
        LLMRouteCandidateProvider,
        RouteProposalError,
    )

    provider = LLMRouteCandidateProvider(api_key="", model="",
                                         base_url="http://localhost:9/v1")
    with pytest.raises(RouteProposalError) as exc:
        provider.propose({"revision": "rev_1"}, source_revision="rev_1",
                         source_digest="digest")
    assert exc.value.code == "BLOCKED_REAL_LLM_PROPOSER_UNAVAILABLE"


def test_plot_and_route_injected_chat_seam_still_works() -> None:
    from novelforge.story_engine.planning.plot_synthesis import (
        LLMPlotCandidateProvider,
    )
    from novelforge.story_engine.planning.route_candidates import (
        LLMRouteCandidateProvider,
    )

    plot = LLMPlotCandidateProvider(chat=lambda _messages: '{"candidates": []}')
    assert plot.propose({}, source_revision="rev_1") == []

    route = LLMRouteCandidateProvider(chat=lambda _messages: '{"candidates": []}')
    assert route.propose({}, source_revision="rev_1", source_digest="d") == []
