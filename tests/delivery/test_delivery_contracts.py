"""V4-07 §7–§11、§15、§19、§32–§33、§43–§44、§51–§53：交付契约与注册表。"""

from __future__ import annotations

import pytest

from novelforge.delivery import (
    DEFAULT_PROFILE,
    DELIVERY_SCHEMA_VERSION,
    EXPORT_FORMATS,
    EXPORT_PROFILES,
    ISSUE_CODES,
    SELECTION_MODES,
    DeliveryFormatError,
    DeliveryIssue,
    DeliveryPolicy,
    DeliverySelection,
    DeliverySnapshot,
    ExporterRegistry,
    ExporterSpec,
    build_default_registry,
    profile_defaults,
)
from novelforge.delivery.errors import DeliverySelectionError


def test_selection_validation_and_defaults() -> None:
    assert SELECTION_MODES == ("accepted", "explicit_revisions", "current")
    assert EXPORT_PROFILES == ("reader", "author", "machine", "audit")
    assert EXPORT_FORMATS == ("json", "markdown", "docx", "nfpack")
    selection = DeliverySelection(novel_id="novel_alpha")
    assert selection.selection_mode == "accepted"      # §8：默认 accepted，不是 current
    assert selection.profile == DEFAULT_PROFILE
    assert selection.request_id.startswith("delivery_")
    with pytest.raises(DeliverySelectionError):
        DeliverySelection(novel_id="")
    with pytest.raises(DeliverySelectionError):
        DeliverySelection(novel_id="n", selection_mode="latest")
    with pytest.raises(DeliverySelectionError):
        DeliverySelection(novel_id="n", profile="whatever")
    with pytest.raises(DeliverySelectionError):
        DeliverySelection(novel_id="n", selection_mode="explicit_revisions")
    with pytest.raises(DeliveryFormatError):
        DeliverySelection(novel_id="n", formats=("epub",))
    with pytest.raises(DeliveryFormatError):
        DeliverySelection(novel_id="n", formats=())


def test_profile_controls_inclusion_and_can_be_overridden() -> None:
    reader = DeliverySelection(novel_id="n", profile="reader")
    assert reader.include_quality is False and reader.provenance_included is False
    audit = DeliverySelection(novel_id="n", profile="audit")
    assert audit.include_quality and audit.provenance_included and \
        audit.history_included and audit.review_included
    override = DeliverySelection(novel_id="n", profile="reader",
                                include_quality_report=True)
    assert override.include_quality is True
    assert profile_defaults("machine")["include_provenance"] is True


def test_policy_defaults_are_strict_and_relaxed_explicit() -> None:
    policy = DeliveryPolicy()
    assert policy.require_accepted is True and policy.require_quality_pass is True
    assert policy.allow_unevaluated is False and policy.allow_stale_quality is False
    assert policy.blocking_severities == ("blocker", "major")
    relaxed = DeliveryPolicy.relaxed()
    assert relaxed.require_accepted is False and relaxed.allow_stale_quality is True
    assert policy.digest != relaxed.digest
    selection = DeliverySelection(novel_id="n", policy=policy)
    assert selection.as_dict()["policy"]["require_accepted"] is True
    assert selection.digest != DeliverySelection(
        novel_id="n", policy=relaxed).digest


def test_selection_digest_is_stable_and_content_sensitive() -> None:
    first = DeliverySelection(novel_id="n", formats=("json", "markdown"))
    second = DeliverySelection(novel_id="n", formats=("markdown", "json"))
    assert first.digest == second.digest          # 顺序无关
    assert first.digest != DeliverySelection(novel_id="n",
                                             formats=("json",)).digest
    assert first.as_dict()["delivery_schema_version"] == DELIVERY_SCHEMA_VERSION


def test_issue_and_snapshot_contract() -> None:
    issue = DeliveryIssue(code="DELIVERY_QUALITY_STALE", severity="blocker",
                          message="stale", node_ids=("sc_001_02",), revision=2)
    assert issue.blocking is True
    assert issue.as_dict()["revision"] == 2
    with pytest.raises(DeliveryFormatError):
        DeliveryIssue(code="X", severity="fatal", message="x")
    snapshot = DeliverySnapshot(snapshot_id="DS_1", novel_id="n",
                                node_revisions={"a": 2}, selection_digest="d")
    assert snapshot.node_ids == ("a",)
    assert snapshot.input_digest and snapshot.as_dict()["schema_version"] == 1
    assert "DELIVERY_QUALITY_STALE" in ISSUE_CODES
    assert "DELIVERY_NO_ACCEPTED_REVISION" in ISSUE_CODES
    assert "DELIVERY_CROSS_NOVEL_REFERENCE" in ISSUE_CODES


def test_exporter_registry_is_extensible_and_versioned() -> None:
    registry = build_default_registry()
    assert registry.formats() == ("docx", "json", "markdown", "nfpack")
    spec = registry.spec("markdown")
    assert spec.exporter_id.startswith("delivery.") and spec.version >= 1
    assert spec.mime_type == "text/markdown" and spec.extension == "md"
    assert registry.spec("docx").text is False
    assert registry.spec("nfpack").extension == "nfpack"
    with pytest.raises(DeliveryFormatError):
        registry.get("epub")
    custom = ExporterRegistry()
    custom.register(ExporterSpec(format="yaml", exporter_id="plugin.yaml.v1",
                                 version=1, mime_type="text/yaml", extension="yaml"),
                    lambda ctx: b"a: 1\n")
    assert custom.get("yaml")[0].exporter_id == "plugin.yaml.v1"
    assert custom.specs()[0].as_dict()["profiles_supported"]
