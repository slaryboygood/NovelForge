"""UtilityService —— 最小 application → ai 集成路径（V4-02 §25）。

目的**不是**引入故事生成（那属于 V4-04），而是证明：

```text
application.services → novelforge.ai（LLMGateway）→ provider
ai 不反向依赖 application
```

这里选择的是一次**通用 utility 操作**：把一段文本映射到给定的候选标签集合。
它不含任何故事语义（不知道 novel / chapter / scene / canon），
且因为是确定性 utility 任务，contract 显式声明 `cacheable=True`（§20 允许）。
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from novelforge.ai import LLMContract, LLMGateway, ModelPolicy, PromptSpec, ValidationPolicy


class UtilityLabels(BaseModel):
    """utility 操作的输出 schema（只含被选中的原始标签）。"""

    model_config = ConfigDict(extra="forbid")
    labels: list[str]


UTILITY_LABEL_CONTRACT = LLMContract(
    contract_id="utility.label_extraction.v1",
    version=1,
    prompt=PromptSpec(
        system=("你是文本归类助手。只能从给定候选标签中选择，不得发明新标签。"
                "只输出 JSON：{\"labels\": [...]}"),
        user_template="候选标签：{labels}\n文本：{text}"),
    output_model=UtilityLabels,
    generation_mode="structured_json",
    temperature_policy="deterministic",
    max_output_tokens=256,
    timeout_s=30.0,
    max_attempts=2,
    cacheable=True,
    validation=ValidationPolicy(require_json=True, retry_on_structured_output=True,
                               strict=False),
)


class UtilityService:
    """最小 utility 能力：依赖注入的 LLMGateway（不自己建 provider）。"""

    def __init__(self, gateway: LLMGateway, *,
                 contract: LLMContract = UTILITY_LABEL_CONTRACT,
                 model_policy: ModelPolicy | None = None) -> None:
        self.gateway = gateway
        self.contract = contract
        self.model_policy = model_policy or ModelPolicy(
            profile="cost_first",
            required_capabilities=contract.required_capabilities)
        self.gateway.registry.register(contract)

    def extract_labels(self, *, text: str, candidates: Sequence[str],
                       request_id: str = "") -> dict[str, Any]:
        """把文本映射到候选标签（越界标签会被 filter 掉，不静默放行）。"""

        if not str(text or "").strip():
            raise ValueError("extract_labels 需要非空文本")
        allowed = [str(item) for item in candidates]
        if not allowed:
            raise ValueError("extract_labels 需要至少一个候选标签")

        result = self.gateway.generate(
            contract=self.contract,
            context={"text": text, "labels": "、".join(allowed)},
            model_policy=self.model_policy,
            operation="utility.label_extraction",
            request_id=request_id)

        chosen = getattr(result.output, "labels", []) or []
        kept = [item for item in chosen if item in allowed]
        dropped = [item for item in chosen if item not in allowed]
        return {"labels": kept, "dropped_out_of_catalog": dropped,
                "request_id": result.request_id, "usage": dict(result.usage),
                "cache": dict(result.cache), "provider": result.provider,
                "model": result.model, "read_only": True}


def utility_service(gateway: LLMGateway, **kwargs: Any) -> UtilityService:
    return UtilityService(gateway, **kwargs)


__all__ = ["UTILITY_LABEL_CONTRACT", "UtilityLabels", "UtilityService",
           "utility_service"]

