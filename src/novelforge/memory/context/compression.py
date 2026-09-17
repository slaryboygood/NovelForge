"""压缩（V4-03 §22）。

```text
Compression Result ≠ Source of Truth
```

每个压缩结果保留 source_ids / source_revision / contract_version；
可用 V4-02 的 `cacheable=True` contract 缓存不可变摘要。

默认实现是**确定性截断**（零模型、零网络）；`GatewayCompressor` 只在显式注入
LLMGateway 时使用，memory 不直接调用 provider（§25）。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Protocol, Sequence

from ..contracts import MemoryItem, utc_now

SUMMARY_CONTRACT_ID = "memory.summary.v1"


class Compressor(Protocol):
    def compress(self, item: MemoryItem, *, target_tokens: int) -> MemoryItem: ...


class NullCompressor:
    """默认：不压缩（只做预算裁剪）。"""

    provider_id = "null"

    def compress(self, item: MemoryItem, *, target_tokens: int) -> MemoryItem:
        return item


class DeterministicTruncatingCompressor:
    """确定性截断压缩：保留开头并标注来源与压缩事实（不产生新的"事实"）。"""

    provider_id = "deterministic_truncate"

    def __init__(self, *, max_chars: int = 240) -> None:
        self.max_chars = max(32, int(max_chars))

    def compress(self, item: MemoryItem, *, target_tokens: int) -> MemoryItem:
        text = item.text
        if len(text) <= self.max_chars:
            return replace(item, token_estimate=0,
                           selection_reason=(item.selection_reason
                                             + ";compressed:noop").strip(";"))
        head = text[: self.max_chars].rstrip()
        summary = f"{head}…（已压缩，原文 {len(text)} 字）"
        source = replace(item.source, metadata={
            **dict(item.source.metadata),
            "compressed": True, "original_chars": len(text),
            "compressor": self.provider_id, "compressed_at": utc_now()})
        return replace(item, text=summary, source=source, token_estimate=0,
                       selection_reason=(item.selection_reason
                                         + ";compressed:truncated").strip(";"))


class GatewayCompressor:
    """经 `novelforge.ai` 的摘要压缩（可选；需要显式注入 Gateway）。"""

    provider_id = "gateway_summary"

    def __init__(self, gateway: Any, *, contract: Any | None = None) -> None:
        self.gateway = gateway
        self.contract = contract or self._default_contract()

    def _default_contract(self) -> Any:
        from novelforge.ai import LLMContract, PromptSpec, ValidationPolicy

        return LLMContract(
            contract_id=SUMMARY_CONTRACT_ID, version=1,
            prompt=PromptSpec(
                system="把给定文本压缩为要点，不得添加新事实。只输出要点文本。",
                user_template="{text}"),
            generation_mode="text", temperature_policy="deterministic",
            max_output_tokens=256, timeout_s=30.0, max_attempts=2,
            cacheable=True,
            validation=ValidationPolicy(require_json=False,
                                        retry_on_structured_output=False))

    def compress(self, item: MemoryItem, *, target_tokens: int) -> MemoryItem:
        result = self.gateway.generate(contract=self.contract,
                                       context={"text": item.text},
                                       operation="memory.summary")
        summary = str(result.output or "").strip() or item.text
        source = replace(item.source, metadata={
            **dict(item.source.metadata),
            "compressed": True, "compressor": self.provider_id,
            "contract_version": f"{self.contract.contract_id}@v{self.contract.version}",
            "compressed_at": utc_now()})
        return replace(item, text=summary, source=source, token_estimate=0,
                       selection_reason=(item.selection_reason
                                         + ";compressed:gateway_summary").strip(";"))


def compress_items(items: Sequence[MemoryItem], *, compressor: Compressor | None,
                   target_tokens: int) -> list[MemoryItem]:
    if compressor is None or isinstance(compressor, NullCompressor):
        return list(items)
    return [compressor.compress(item, target_tokens=target_tokens) for item in items]


__all__ = [
    "Compressor", "DeterministicTruncatingCompressor", "GatewayCompressor",
    "NullCompressor", "SUMMARY_CONTRACT_ID", "compress_items",
]

