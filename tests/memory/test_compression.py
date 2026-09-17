"""压缩（V4-03 §22、§25）。"""

from __future__ import annotations

from novelforge.memory import (
    ContextBuilder,
    ContextRequest,
    DeterministicTruncatingCompressor,
    GatewayCompressor,
    MemoryItem,
    MemorySource,
)
from support import build_fake_gateway, build_novel, service_for


def _long_item() -> MemoryItem:
    return MemoryItem(memory_id="canon_fact:BIG", memory_type="canon",
                      text="很长的既有事实。" * 60,
                      source=MemorySource(source_type="canon_fact",
                                          source_id="FACT_BIG", revision=3),
                      selection_reason="required_canon")


def test_deterministic_compression_keeps_provenance() -> None:
    compressor = DeterministicTruncatingCompressor(max_chars=50)
    item = _long_item()
    compressed = compressor.compress(item, target_tokens=10)
    assert len(compressed.text) < len(item.text)
    assert "已压缩" in compressed.text
    assert compressed.source.source_id == item.source.source_id
    assert compressed.source.revision == item.source.revision
    assert "compressed:truncated" in compressed.selection_reason
    assert compressed.source.metadata["compressor"] == "deterministic_truncate"


def test_gateway_compression_uses_llm_gateway_contract() -> None:
    gateway, provider = build_fake_gateway(["要点：备用电源被破坏"])
    compressor = GatewayCompressor(gateway)
    compressed = compressor.compress(_long_item(), target_tokens=20)
    assert provider.calls == 1, "必须经 LLMGateway 调用（零网络 stub）"
    assert compressed.text == "要点：备用电源被破坏"
    assert compressed.source.metadata["contract_version"] == "memory.summary.v1@v1"
    assert compressed.source.source_id == "FACT_BIG", "摘要不得丢失来源"


def test_gateway_compression_result_is_cached_and_not_truth() -> None:
    gateway, provider = build_fake_gateway(["摘要一", "摘要二"])
    compressor = GatewayCompressor(gateway)
    first = compressor.compress(_long_item(), target_tokens=20)
    second = compressor.compress(_long_item(), target_tokens=20)
    assert first.text == second.text == "摘要一"
    assert provider.calls == 1, "cacheable contract 命中缓存，不重复调用"


def test_context_builder_applies_compressor() -> None:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        build_novel(tmp_path, "novel_alpha", title="阿尔法计划",
                    fact_text="主角不会使用枪械")
        service = service_for(tmp_path, "novel_alpha")
        builder = ContextBuilder(
            service, compressor=DeterministicTruncatingCompressor(max_chars=20))
        bundle = builder.build(ContextRequest(novel_id="novel_alpha",
                                              task="下一场戏", token_budget=200))
        assert bundle.blocks["required.canon"].items
        assert all("compressed:" in item.selection_reason
                   for item in bundle.blocks["required.canon"].items)

