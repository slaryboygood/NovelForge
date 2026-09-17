"""LLM Contract（V4-02，版本化）。

调用方只提供 `contract` + `context` + `model_policy`；temperature、token 上限、
重试策略、输出 schema 都由 contract 决定，避免调用方到处传 provider 参数。

注意（模块边界）：contract 只描述**通用生成任务**，不包含任何故事语义
（没有 novel / chapter / scene / canon 概念）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from pydantic import BaseModel

from .errors import ProviderConfigurationError

GenerationMode = Literal["structured_json", "text"]
TemperaturePolicy = Literal["deterministic", "balanced", "creative"]

#: 策略 → temperature（0 = 确定性，便于结构化抽取；不含任何业务语义）
TEMPERATURE_BY_POLICY: dict[str, float] = {
    "deterministic": 0.0,
    "balanced": 0.4,
    "creative": 0.9,
}


@dataclass(frozen=True)
class PromptSpec:
    """最小 prompt 模板（V4-02 不做大规模 prompt 设计）。

    `system` 与 `user_template` 都属于 contract；`user_template` 通过 `context`
    中的键做 `str.format` 展开（缺失键 → `ProviderConfigurationError`，避免静默空 prompt）。
    """

    system: str
    user_template: str

    def render(self, context: Mapping[str, Any]) -> tuple[str, str]:
        try:
            rendered = self.user_template.format(**dict(context))
        except KeyError as exc:
            raise ProviderConfigurationError(
                f"contract 需要的 context 键缺失：{exc.args[0]}",
                details={"missing_context_key": str(exc.args[0])}) from exc
        return self.system, rendered


@dataclass(frozen=True)
class ValidationPolicy:
    """输出校验策略。"""

    require_json: bool = True
    retry_on_structured_output: bool = True
    strict: bool = True


@dataclass(frozen=True)
class LLMContract:
    contract_id: str
    version: int
    prompt: PromptSpec
    output_model: type[BaseModel] | None = None
    generation_mode: GenerationMode = "structured_json"
    temperature_policy: TemperaturePolicy = "deterministic"
    max_output_tokens: int = 2000
    timeout_s: float = 60.0
    max_attempts: int = 3
    #: 默认 False：只有明确声明可缓存的（utility / 确定性转换）才进入缓存
    cacheable: bool = False
    validation: ValidationPolicy = field(default_factory=ValidationPolicy)
    required_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.contract_id or "").strip():
            raise ProviderConfigurationError("contract_id 不能为空")
        if int(self.version) < 1:
            raise ProviderConfigurationError("contract_version 必须 >= 1")
        if self.generation_mode == "structured_json" and not self.validation.require_json:
            raise ProviderConfigurationError(
                "structured_json contract 必须 require_json=True")
        if self.generation_mode == "text" and self.validation.require_json:
            raise ProviderConfigurationError(
                "text contract 必须显式使用 ValidationPolicy(require_json=False)"
                "（需要 JSON 输出请用 generation_mode='structured_json'）")
        if self.max_attempts < 1:
            raise ProviderConfigurationError("max_attempts 必须 >= 1")
        if self.timeout_s <= 0:
            raise ProviderConfigurationError("timeout_s 必须 > 0")

    @property
    def temperature(self) -> float:
        return TEMPERATURE_BY_POLICY[self.temperature_policy]

    @property
    def schema_id(self) -> str:
        if self.output_model is None:
            return ""
        return getattr(self.output_model, "__name__", str(self.output_model))

    def as_dict(self) -> dict[str, Any]:
        return {"contract_id": self.contract_id, "contract_version": self.version,
                "generation_mode": self.generation_mode,
                "temperature_policy": self.temperature_policy,
                "max_output_tokens": self.max_output_tokens,
                "timeout_s": self.timeout_s, "max_attempts": self.max_attempts,
                "cacheable": self.cacheable, "schema_id": self.schema_id,
                "required_capabilities": list(self.required_capabilities)}


class ContractRegistry:
    """进程内 contract 注册表（确定性、可测试）。"""

    def __init__(self) -> None:
        self._contracts: dict[tuple[str, int], LLMContract] = {}

    def register(self, contract: LLMContract) -> LLMContract:
        key = (contract.contract_id, contract.version)
        existing = self._contracts.get(key)
        if existing is not None and existing != contract:
            raise ProviderConfigurationError(
                f"contract 重复注册且内容不同：{contract.contract_id}@v{contract.version}")
        self._contracts[key] = contract
        return contract

    def get(self, contract_id: str, version: int | None = None) -> LLMContract:
        if version is not None:
            contract = self._contracts.get((contract_id, int(version)))
            if contract is None:
                raise ProviderConfigurationError(
                    f"未注册的 contract：{contract_id}@v{version}",
                    details={"contract_id": contract_id, "contract_version": version})
            return contract
        candidates = [item for (cid, _), item in self._contracts.items()
                      if cid == contract_id]
        if not candidates:
            raise ProviderConfigurationError(
                f"未注册的 contract：{contract_id}",
                details={"contract_id": contract_id})
        return max(candidates, key=lambda item: item.version)

    def ids(self) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(self._contracts))

    def __len__(self) -> int:
        return len(self._contracts)


DEFAULT_CONTRACTS = ContractRegistry()


def resolve_contract(contract: LLMContract | str, *, registry: ContractRegistry | None = None,
                     version: int | None = None) -> LLMContract:
    """接受 contract 对象或 `contract_id` 字符串（后者从注册表解析）。"""

    if isinstance(contract, LLMContract):
        return contract
    return (registry or DEFAULT_CONTRACTS).get(str(contract), version)


__all__ = [
    "ContractRegistry", "DEFAULT_CONTRACTS", "GenerationMode", "LLMContract",
    "PromptSpec", "TEMPERATURE_BY_POLICY", "TemperaturePolicy", "ValidationPolicy",
    "resolve_contract",
]
