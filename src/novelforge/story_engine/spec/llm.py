"""M3：SpecProposal 的 LLM provider —— 只产出**提案**，永不直接成为 truth。

约束：

- 输出必须过 strict schema（`SpecProposal.model_validate(..., strict=True)`）；
- 解析 / 校验失败最多重试 3 次（2s / 5s / 10s backoff），保留原始响应文本；
- 结果必须再由作者确认（`SpecConfirmation`）才能进入编译。

## V4-02 迁移说明（compatibility adapter）

本模块是 **legacy 调用点**：V4-02 起它不再自己发 HTTP 请求，而是通过唯一的
`novelforge.ai` LLMGateway 调用模型（timeout / retry / 错误归一化 / usage / trace
全部由 Gateway 负责）。

保留的兼容面（**不要扩展**）：

```text
LLMSpecProposalProvider(api_key=..., model=..., endpoint=..., timeout=..., max_attempts=...,
                        chat=...)   ← chat 注入是测试 seam，不是产品路径
SpecProposalError / SpecProposalProvider / StaticSpecProposalProvider
build_spec_prompt / extract_proposal_payload / propose_spec / load_env / BACKOFF
```

已移除的硬编码（V4-02 §9）：

```text
DEFAULT_MODEL / DEFAULT_ENDPOINT（原先写死 deepseek-chat 与厂商端点）
→ model / base_url / api_key_env 现在全部由调用方或 environment 提供
```
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import ValidationError

from .models import NovelSpec, SpecGap, SpecProposal, new_spec_id

BACKOFF = (2.0, 5.0, 10.0)

SYSTEM_PROMPT = (
    "你是小说规格补全助手，只输出建议，不写正文、不改写作者已确认的内容。"
    "输入是 NOVEL_SPEC（可能留空）与缺口列表；请为每个缺口给出一个具体、题材无关的建议值。"
    "输出严格 JSON：{\"fields\":[{\"field\":\"...\",\"value\":...,\"rationale\":\"...\","
    "\"confidence\":0.0}]}"
    "。允许的 field 只能来自缺口列表；world_seed / characters_seed 这类列表字段请按输入结构给数组。"
    "只输出 JSON，不要解释。")

ChatFunction = Callable[[list[dict[str, str]]], str]


class SpecProposalError(RuntimeError):
    def __init__(self, code: str, message: str, *, raw: str = "") -> None:
        self.code = code
        self.message = message
        self.raw = raw
        super().__init__(f"{code}: {message}")


class SpecProposalProvider(Protocol):
    def propose(self, spec: NovelSpec, gaps: list[SpecGap]) -> SpecProposal: ...


def load_env(project_root: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    env_file = project_root / ".env.local"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("DEEPSEEK_API_KEY", "ARK_API_KEY"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def build_spec_prompt(spec: NovelSpec, gaps: list[SpecGap]) -> str:
    return "\n".join([
        "当前 NOVEL_SPEC：", spec.model_dump_json(exclude={"created_at"}),
        "", "缺口列表：",
        json.dumps([gap.model_dump(mode="json") for gap in gaps], ensure_ascii=False),
        "", "请只针对缺口字段给出建议值。"])


def extract_proposal_payload(raw: str, *, proposal_id: str, spec: NovelSpec,
                             provider: str, model: str) -> SpecProposal:
    """把 LLM 原始响应解析成严格 SpecProposal（schema mismatch 一律拒绝）。"""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SpecProposalError("SPEC_PROPOSAL_JSON_INVALID", str(exc)[:200], raw=raw) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("fields"), list):
        raise SpecProposalError("SPEC_PROPOSAL_SHAPE_INVALID",
                                "响应必须是 {\"fields\": [...]}", raw=raw)
    document = {
        "proposal_id": proposal_id, "spec_id": spec.spec_id, "novel_id": spec.novel_id,
        "provider": provider, "model": model,
        "fields": payload["fields"],
    }
    try:
        return SpecProposal.model_validate(document, strict=True)
    except ValidationError as exc:
        raise SpecProposalError("SPEC_PROPOSAL_SCHEMA_INVALID",
                                str(exc)[:300], raw=raw) from exc


class StaticSpecProposalProvider:
    """测试 / fixture 用：直接给出提案字段（仍走 strict schema）。"""

    def __init__(self, fields: list[dict[str, Any]], *, provider: str = "static",
                 model: str = "static") -> None:
        self.fields = fields
        self.provider = provider
        self.model = model

    def propose(self, spec: NovelSpec, gaps: list[SpecGap]) -> SpecProposal:
        payload = {"fields": self.fields}
        raw = json.dumps(payload, ensure_ascii=False)
        return extract_proposal_payload(raw, proposal_id=new_spec_id("PROPOSAL"),
                                        spec=spec, provider=self.provider, model=self.model)


class LLMSpecProposalProvider:
    """真实 LLM provider（compatibility adapter over `novelforge.ai`）。

    `chat` 注入保留为测试 seam；未注入时每次调用都经 LLMGateway：
    模型 / base_url / api_key 环境变量必须由调用方提供，模块内不再有默认生产模型。
    """

    #: 兼容默认：这些环境变量按顺序作为 api_key 来源（与 .env.example 保持一致）
    DEFAULT_KEY_ENVS: tuple[str, ...] = ("DEEPSEEK_API_KEY", "ARK_API_KEY")
    #: 兼容默认：模型名的环境变量（未显式传 model 时使用）
    MODEL_ENV = "NOVELFORGE_SPEC_MODEL"
    #: 兼容默认：base_url 的环境变量
    BASE_URL_ENV = "NOVELFORGE_SPEC_BASE_URL"

    def __init__(self, *, api_key: str = "", model: str = "",
                 endpoint: str = "", timeout: float = 150.0,
                 max_attempts: int = 3, chat: ChatFunction | None = None,
                 project_root: Path | str | None = None,
                 provider_id: str = "spec_proposal",
                 model_policy: Any | None = None,
                 gateway: Any | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.project_root = Path(project_root) if project_root else None
        self.provider_id = provider_id
        self._model_policy = model_policy
        self._gateway = gateway
        self._injected = chat is not None
        self._chat = chat or self._gateway_chat

    def propose(self, spec: NovelSpec, gaps: list[SpecGap]) -> SpecProposal:
        prompt = build_spec_prompt(spec, gaps)
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}]
        last_error: SpecProposalError | None = None
        for attempt in range(1, self.max_attempts + 1):
            if attempt > 1 and last_error is not None:
                messages = messages[:2] + [{
                    "role": "user",
                    "content": f"上一次输出未通过校验：{last_error.message[:200]}。"
                               "请只输出合法 JSON 对象。"}]
            raw = self._chat(messages)
            try:
                return extract_proposal_payload(raw, proposal_id=new_spec_id("PROPOSAL"),
                                                spec=spec, provider="llm",
                                                model=self.model)
            except SpecProposalError as error:
                last_error = error
                if attempt < self.max_attempts:
                    time.sleep(BACKOFF[min(attempt - 1, len(BACKOFF) - 1)])
        assert last_error is not None
        raise last_error

    # ------------------------------------------------------------ gateway 路径
    def _resolved_env(self) -> dict[str, str]:
        env = dict(load_env(self.project_root)) if self.project_root else {}
        for key in self.DEFAULT_KEY_ENVS:
            if os.environ.get(key):
                env[key] = os.environ[key]
        return env

    def _resolve_api_key(self, env: dict[str, str]) -> str:
        if self.api_key:
            return self.api_key
        for key in self.DEFAULT_KEY_ENVS:
            if env.get(key):
                return env[key]
        return ""

    def _ensure_contract(self, model: str) -> None:
        """准备 contract / model policy（不构建 provider；注入 gateway 时也复用）。"""

        from novelforge.ai import (LLMContract, ModelPolicy, PromptSpec,
                                   ValidationPolicy)

        if getattr(self, "_contract", None) is not None:
            return
        self._spec_prompt = PromptSpec(system=SYSTEM_PROMPT,
                                       user_template="{prompt}")
        self._contract = LLMContract(
            contract_id="spec_proposal.v1", version=1, prompt=self._spec_prompt,
            generation_mode="text", temperature_policy="deterministic",
            max_output_tokens=2000, timeout_s=float(self.timeout),
            max_attempts=1,  # 重试由本适配器统一管理（保持既有语义）
            cacheable=False,
            validation=ValidationPolicy(require_json=False,
                                        retry_on_structured_output=False))
        if self._model_policy is None:
            if self._gateway is not None:
                # 注入 gateway 时由调用方决定 provider，只按模型名路由
                self._model_policy = ModelPolicy(profile="explicit_model",
                                                 explicit_model_id=model)
            else:
                self._model_policy = ModelPolicy(
                    profile="explicit_model", explicit_provider_id=self.provider_id,
                    explicit_model_id=model)

    def _build_gateway(self, env: dict[str, str]):
        """用显式配置（或 environment）构建一次性 Gateway（V4-02 唯一模型入口）。"""

        from novelforge.ai import (
            LLMContract,
            ModelPolicy,
            ModelSpec,
            PromptSpec,
            ProviderConfig,
            build_gateway_from_configs,
            load_provider_configs,
        )
        from novelforge.observability import InMemoryModelTraceStore

        api_key = self._resolve_api_key(env)
        if not api_key:
            raise SpecProposalError(
                "BLOCKED_REAL_LLM_PROPOSER_UNAVAILABLE",
                "缺少 API key（请设置 "
                + " / ".join(self.DEFAULT_KEY_ENVS)
                + "，或使用 providers 配置）")

        model = self.model or env.get(self.MODEL_ENV, "")
        if not model:
            raise SpecProposalError(
                "BLOCKED_REAL_LLM_PROPOSER_UNAVAILABLE",
                f"缺少模型名（请显式传入 model 或设置 {self.MODEL_ENV}）")
        base_url = self.endpoint or env.get(self.BASE_URL_ENV, "")
        if not base_url:
            raise SpecProposalError(
                "BLOCKED_REAL_LLM_PROPOSER_UNAVAILABLE",
                f"缺少 base_url（请显式传入 endpoint 或设置 {self.BASE_URL_ENV}）")
        if base_url.endswith("/chat/completions"):
            base_url = base_url[: -len("/chat/completions")]

        self._ensure_contract(model)
        config = ProviderConfig(
            provider_id=self.provider_id, kind="openai_compatible",
            base_url=base_url,
            # key 已解析出来 → 走一次性环境变量，不落盘、不写入 trace
            api_key_env="NOVELFORGE_SPEC_API_KEY",
            models=(ModelSpec(model_id=model, capabilities=("utility",),
                              cost_tier=3, speed_tier=3),),
            default_model=model, timeout_s=float(self.timeout), enabled=True)
        registry = load_provider_configs(payload={"providers": []}, env=env)
        registry.register(config)
        gateway = build_gateway_from_configs(
            tuple(registry.all()), contracts=None,
            trace_sink=InMemoryModelTraceStore(),
            env={**env, "NOVELFORGE_SPEC_API_KEY": api_key})
        return gateway

    def _gateway_chat(self, messages: list[dict[str, str]]) -> str:
        """经 LLMGateway 调用模型；错误统一映射回 legacy SpecProposalError。"""

        from novelforge.ai import LLMError

        env = self._resolved_env()
        if self._gateway is None:
            self._gateway = self._build_gateway(env)
        elif getattr(self, "_contract", None) is None:
            self._ensure_contract(self.model or "injected-model")
        gateway = self._gateway
        user_content = messages[-1]["content"] if messages else ""
        try:
            result = gateway.generate(
                contract=self._contract,
                context={"prompt": user_content},
                model_policy=self._model_policy,
                operation="spec_proposal")
        except LLMError as exc:
            # RetryExhaustedError 保留根因错误码；据此映射回 legacy 错误码
            effective = str((exc.details or {}).get("last_error_code") or exc.code)
            http_codes = {"LLM_AUTHENTICATION_ERROR", "LLM_RATE_LIMIT",
                          "LLM_PROVIDER_UNAVAILABLE", "LLM_INVALID_REQUEST",
                          "LLM_MODEL_UNAVAILABLE", "LLM_REQUEST_TIMEOUT",
                          "LLM_PROVIDER_CONFIGURATION_ERROR"}
            legacy_code = ("SPEC_PROPOSAL_HTTP_FAILURE" if effective in http_codes
                           else "SPEC_PROPOSAL_NETWORK_FAILURE")
            raise SpecProposalError(legacy_code, exc.message[:200]) from exc
        except Exception as exc:  # noqa: BLE001 - 统一成 proposal 层错误
            raise SpecProposalError("SPEC_PROPOSAL_NETWORK_FAILURE",
                                    str(exc)[:200]) from exc
        text = str(result.output or "")
        if not text.strip():
            raise SpecProposalError("SPEC_PROPOSAL_EMPTY_RESPONSE", "模型返回空内容")
        return text


def propose_spec(spec: NovelSpec, gaps: list[SpecGap],
                 provider: SpecProposalProvider) -> SpecProposal:
    """统一入口：任何 provider 的提案都必须通过 strict schema 与 spec 归属检查。"""

    proposal = provider.propose(spec, gaps)
    if proposal.spec_id != spec.spec_id:
        raise SpecProposalError("SPEC_PROPOSAL_SPEC_MISMATCH",
                                f"{proposal.spec_id} != {spec.spec_id}")
    if proposal.novel_id and proposal.novel_id != spec.novel_id:
        raise SpecProposalError("SPEC_PROPOSAL_NOVEL_MISMATCH",
                                f"{proposal.novel_id} != {spec.novel_id}")
    known = {gap.field for gap in gaps}
    unknown = [name for name in proposal.field_names() if name not in known]
    if unknown:
        raise SpecProposalError("SPEC_PROPOSAL_FIELD_NOT_IN_GAPS", ", ".join(unknown))
    return proposal


__all__ = [
    "BACKOFF",
    "LLMSpecProposalProvider",
    "SYSTEM_PROMPT",
    "SpecProposalError",
    "SpecProposalProvider",
    "StaticSpecProposalProvider",
    "build_spec_prompt",
    "extract_proposal_payload",
    "load_env",
    "propose_spec",
]
