"""M3：SpecProposal 的 LLM provider —— 只产出**提案**，永不直接成为 truth。

约束：

- 输出必须过 strict schema（`SpecProposal.model_validate(..., strict=True)`）；
- 解析 / 校验失败最多重试 3 次（2s / 5s / 10s backoff），保留原始响应文本；
- 结果必须再由作者确认（`SpecConfirmation`）才能进入编译；
- 网络调用通过注入的 `chat` 函数完成，便于测试与替换 provider。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import ValidationError

from .models import NovelSpec, SpecGap, SpecProposal, new_spec_id

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_ENDPOINT = "https://api.deepseek.com/chat/completions"
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
    """真实 LLM provider：默认走 DeepSeek chat completions；`chat` 可注入替换。"""

    def __init__(self, *, api_key: str = "", model: str = DEFAULT_MODEL,
                 endpoint: str = DEFAULT_ENDPOINT, timeout: float = 150.0,
                 max_attempts: int = 3, chat: ChatFunction | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_attempts = max_attempts
        self._injected = chat is not None
        self._chat = chat or self._http_chat

    def propose(self, spec: NovelSpec, gaps: list[SpecGap]) -> SpecProposal:
        if not self.api_key and not self._injected:
            raise SpecProposalError("BLOCKED_REAL_LLM_PROPOSER_UNAVAILABLE",
                                    "缺少 DEEPSEEK_API_KEY")
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

    def _http_chat(self, messages: list[dict[str, str]]) -> str:
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps({"model": self.model, "messages": messages, "temperature": 0,
                             "max_tokens": 2000,
                             "response_format": {"type": "json_object"}}).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            raise SpecProposalError("SPEC_PROPOSAL_HTTP_FAILURE",
                                    f"HTTP {exc.code}", raw=exc.read().decode(
                                        "utf-8", "replace")[:2000]) from exc
        except Exception as exc:  # noqa: BLE001 - 统一成 proposal 层错误
            raise SpecProposalError("SPEC_PROPOSAL_NETWORK_FAILURE",
                                    str(exc)[:200]) from exc
        choices = body.get("choices") or []
        content = choices[0].get("message", {}).get("content") if choices else ""
        if not content:
            raise SpecProposalError("SPEC_PROPOSAL_EMPTY_RESPONSE", "模型返回空内容")
        return content


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
    "DEFAULT_ENDPOINT",
    "DEFAULT_MODEL",
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
