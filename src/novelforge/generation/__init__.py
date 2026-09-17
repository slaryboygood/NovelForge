"""NovelForge `generation` —— Structured Story Blueprint Generation（V4-04）。

Public Contract（保持精简，§7）：

```text
BlueprintGenerationService   唯一生成入口（逐级生成 / 局部重生成 / 接受）
GenerationRequest            生成请求（task / node / parent / expected_revision /
                             preserve / idempotency_key / model_policy）
GenerationResult             统一结果（node / revision / contract / model /
                             context_digest / source_ids / usage / trace / validation / evidence）
GenerationPlan               流水线计划（premise → … → links）
GenerationEvidence           可追溯证据（contract / context digest / model / parent revision）
TaskSpec / TaskRegistry      版本化任务契约（blueprint.<task>.v1）
DEFAULT_PIPELINE             默认逐级生成顺序（禁止"整本大纲一次生成"）
GenerationError 家族
```

边界：

```text
generation → ai（LLMGateway）、memory（ContextBuilder）、blueprint（节点模型 + repository）、
             core、persistence（仅经 blueprint repository / paths）
禁止        直接 import provider 实现 / HTTP client / Canon / StoryState / api
```

生成结果是 **proposal**：默认 `status="proposed"`，不写 Canon / StoryState（ADR-017）。
"""

from .contracts import CONTRACT_VERSION, TaskRegistry, TaskSpec
from .errors import (
    GenerationError,
    GenerationUnavailableError,
    GenerationValidationError,
    RewriteViolationError,
)
from .service import (
    DEFAULT_PIPELINE,
    NODE_TYPE_TASK,
    BlueprintGenerationService,
    GenerationEvidence,
    GenerationPlan,
    GenerationRequest,
    GenerationResult,
    default_registry,
    task_for_node_type,
)
from .rewrite import (
    REWRITE_CONTRACT_VERSION,
    assert_rewrite_allowed,
    build_rewrite_contract,
    changed_outside_target,
    merge_target_fields,
    rewrite_contract_id,
)

__all__ = [
    "BlueprintGenerationService", "GenerationRequest", "GenerationResult",
    "GenerationPlan", "GenerationEvidence", "TaskSpec", "TaskRegistry",
    "DEFAULT_PIPELINE", "CONTRACT_VERSION", "default_registry",
    "GenerationError", "GenerationUnavailableError", "GenerationValidationError",
    # V4-06：字段级 AI 改写（只改 target fields）
    "NODE_TYPE_TASK", "task_for_node_type", "RewriteViolationError",
    "REWRITE_CONTRACT_VERSION", "rewrite_contract_id", "build_rewrite_contract",
    "assert_rewrite_allowed", "changed_outside_target", "merge_target_fields",
]
