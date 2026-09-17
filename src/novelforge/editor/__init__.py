"""NovelForge `editor` —— Blueprint Editor & Revision Workflow（V4-06）。

Public Contract（精简，§6）：

```text
BlueprintEditorService                编辑能力入口（读 revision / 改字段 / 比较 / 记录）
EditRequest / EditResult              手工字段级修改
BatchEditRequest / BatchEditResult    多节点修改（先全量校验，默认 all_or_rollback）
DiffRequest / BlueprintDiff           结构化比较（零模型，确定性）
RewriteRequest / RewriteResult        AI 只改指定字段
ApprovalResult                        accept / reject（reject 只记录，不删 revision）
RestoreResult                         restore / undo（用旧内容创建新 revision）
ChangeImpact                          修改影响面（只报告，不自动改下游）
RevisionView / RevisionHistory        revision 导航（来源 = BlueprintRepository）
EditorOperationRecord / ReviewDecision 审计（editor metadata，不是 story truth）
EditorSession / MoveNodeRequest       轻量会话 / 结构移动
EditorError 家族
```

边界（§65–§67）：

```text
editor        → blueprint（唯一 truth）/ generation（AI 改写 / 重生成）/ core / persistence.paths
禁止          → editor import api / application / ai provider / memory / story_engine；
                editor 不持有第二套 Blueprint store；不写 Canon / StoryState；
                不自行 memory retrieval；不自行拼 artifact 路径
反向          → 任何下层（core / persistence / domain / ai / memory / blueprint /
                generation / quality）不得 import editor
Application   → application.services.editor 负责把 editor 与 quality 组合（§67）
```

三条铁律：

```text
APPEND_ONLY              所有编辑产生新 revision；accepted 不被静默覆盖
OPTIMISTIC_CONCURRENCY   写操作携带 expected_revision；冲突不覆盖
QUALITY_IS_NOT_APPROVAL  quality_status = passed ≠ status = accepted（§69）
```
"""

from .contracts import (
    AUTHOR_KINDS,
    BATCH_POLICIES,
    EDIT_STATUSES,
    OPERATION_KINDS,
    REVIEW_DECISIONS,
    ApprovalResult,
    BatchEditRequest,
    BatchEditResult,
    ChangeImpact,
    DiffRequest,
    EditRequest,
    EditResult,
    EditorOperationRecord,
    EditorSession,
    MoveNodeRequest,
    RestoreResult,
    ReviewDecision,
    RevisionHistory,
    RevisionView,
    RewriteRequest,
    RewriteResult,
)
from .diff import BlueprintDiff, FieldChange, ListChange, diff_payloads
from .errors import (
    EditorConflictError,
    EditorError,
    EditorNotFoundError,
    EditorOperationRejected,
    EditorOwnershipError,
    EditorPreserveViolation,
    EditorValidationError,
)
from .history import build_history, revision_view
from .impact import compute_impact
from .operations import EditorStore
from .patch import (
    PROTECTED_FIELDS,
    STRUCTURAL_FIELDS,
    editable_fields,
    merge_changes,
    validate_changes,
)
from .service import BlueprintEditorService

__all__ = [
    # service / store
    "BlueprintEditorService", "EditorStore",
    # editing
    "EditRequest", "EditResult", "BatchEditRequest", "BatchEditResult",
    "MoveNodeRequest", "ApprovalResult", "RestoreResult",
    # revision
    "DiffRequest", "RevisionView", "RevisionHistory", "BlueprintDiff",
    "FieldChange", "ListChange", "ChangeImpact",
    # ai rewrite
    "RewriteRequest", "RewriteResult",
    # audit
    "EditorOperationRecord", "ReviewDecision", "EditorSession",
    # helpers / 常量
    "AUTHOR_KINDS", "BATCH_POLICIES", "EDIT_STATUSES", "OPERATION_KINDS",
    "REVIEW_DECISIONS", "PROTECTED_FIELDS", "STRUCTURAL_FIELDS",
    "build_history", "compute_impact", "diff_payloads", "editable_fields",
    "merge_changes", "revision_view", "validate_changes",
    # errors
    "EditorConflictError", "EditorError", "EditorNotFoundError",
    "EditorOperationRejected", "EditorOwnershipError", "EditorPreserveViolation",
    "EditorValidationError",
]
