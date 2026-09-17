"""OpenAI-compatible Provider（V4-02 §8）。

同一份实现通过配置驱动：base_url / model / api_key_env 全部外部注入，
因此 OpenAI / DeepSeek / Ark-compatible / 自建兼容服务都使用这一个 adapter，
不按厂商名字复制 provider。

HTTP 细节：

```text
connect timeout / read timeout 分开（§16）；transport 可注入，测试完全离线
错误归一化：401/403 → AuthenticationError；429 → RateLimitError；
            5xx / 连接错误 → ProviderUnavailableError；超时 → RequestTimeoutError；
            400/422 → InvalidRequestError；404/模型不存在 → ModelUnavailableError
secret 只用于 Authorization header，并会在错误文本中被 redact
```
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from ..config import ProviderConfig, redact_secrets, resolve_secret
from ..errors import (
    AuthenticationError,
    InvalidRequestError,
    ModelUnavailableError,
    ProviderUnavailableError,
    RateLimitError,
    RequestTimeoutError,
)
from ..provider import LLMRequest, ProviderResponse

#: transport(url, headers, payload, *, timeout_s, connect_timeout_s) -> (status, body_text)
Transport = Callable[..., tuple[int, str]]


def default_transport(url: str, headers: Mapping[str, str], payload: Mapping[str, Any],
                      *, timeout_s: float, connect_timeout_s: float | None = None
                      ) -> tuple[int, str]:
    """默认 HTTP transport（httpx；只在真正调用真实 API 时才会被使用）。"""

    import httpx  # 延迟导入：单测用注入 transport，不依赖网络栈

    timeout = httpx.Timeout(timeout_s, connect=connect_timeout_s or timeout_s)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=dict(headers), json=dict(payload))
        return response.status_code, response.text


class OpenAICompatibleProvider:
    """OpenAI-compatible chat completions provider。"""

    def __init__(self, config: ProviderConfig, *,
                 transport: Transport | None = None,
                 env: Mapping[str, str] | None = None) -> None:
        self.config = config
        self.provider_id = config.provider_id
        self._transport = transport or default_transport
        self._env = env

    # ------------------------------------------------------------------ 内部
    def _endpoint(self) -> str:
        base = self.config.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _headers(self) -> dict[str, str]:
        secret = resolve_secret(self.config.api_key_env, env=self._env)
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {secret}"}
        return headers

    def _payload(self, request: LLMRequest, *, supports_json_mode: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages(),
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
        }
        if request.expect_json and supports_json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    @staticmethod
    def _extract_text(body: Any) -> tuple[str, dict[str, Any], str]:
        choices = body.get("choices") or []
        if not choices:
            return "", {}, ""
        choice = choices[0] or {}
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):  # 部分兼容实现返回分片内容数组
            content = "".join(str(part.get("text", "")) if isinstance(part, Mapping)
                              else str(part) for part in content)
        return (str(content or ""),
                dict(body.get("usage") or {}),
                str(choice.get("finish_reason") or ""))

    def _normalize_http_error(self, status: int, body_text: str, *,
                              secrets: tuple[str, ...]) -> Exception:
        detail = redact_secrets(body_text[:500], secrets)
        common = {"provider": self.provider_id, "model": "",
                  "details": {"status": status, "body": detail}}
        if status in (401, 403):
            return AuthenticationError("模型服务鉴权失败（检查 api_key_env 指向的环境变量）",
                                       **common)
        if status == 429:
            return RateLimitError("模型服务限流（429）", **common)
        if status == 404:
            return ModelUnavailableError("模型或端点不存在（404）", **common)
        if status in (400, 422):
            return InvalidRequestError("模型服务拒绝了请求（请求非法）", **common)
        if 500 <= status < 600:
            return ProviderUnavailableError(f"模型服务暂时不可用（{status}）", **common)
        return ProviderUnavailableError(f"模型服务返回未预期状态：{status}", **common)

    # ------------------------------------------------------------------ 调用
    def complete(self, request: LLMRequest) -> ProviderResponse:
        spec = self.config.model(request.model)
        supports_json_mode = bool(spec.supports_json_mode) if spec else True
        headers = self._headers()
        secret = headers.get("Authorization", "").removeprefix("Bearer ")
        payload = self._payload(request, supports_json_mode=supports_json_mode)
        try:
            status, body_text = self._transport(
                self._endpoint(), headers, payload,
                timeout_s=request.timeout_s,
                connect_timeout_s=self.config.connect_timeout_s)
        except TimeoutError as exc:
            raise RequestTimeoutError(
                f"模型调用超时（{request.timeout_s}s）",
                provider=self.provider_id, model=request.model) from exc
        except Exception as exc:  # noqa: BLE001 - 连接层任何异常都归一化
            message = redact_secrets(str(exc)[:300], (secret,))
            if "timeout" in message.lower() or "timed out" in message.lower():
                raise RequestTimeoutError(message, provider=self.provider_id,
                                          model=request.model) from exc
            raise ProviderUnavailableError(
                f"模型服务连接失败：{message}", provider=self.provider_id,
                model=request.model) from exc

        if status != 200:
            raise self._normalize_http_error(status, body_text, secrets=(secret,))

        try:
            body = json.loads(body_text or "{}")
        except json.JSONDecodeError as exc:
            raise ProviderUnavailableError(
                "模型服务返回的不是合法 JSON",
                provider=self.provider_id, model=request.model,
                details={"error": str(exc)[:200]}) from exc

        text, usage_raw, finish_reason = self._extract_text(body)
        return ProviderResponse(text=text, model=str(body.get("model") or request.model),
                                usage_raw=usage_raw, finish_reason=finish_reason,
                                raw_safe={"id": str(body.get("id") or "")})


__all__ = ["OpenAICompatibleProvider", "Transport", "default_transport"]
