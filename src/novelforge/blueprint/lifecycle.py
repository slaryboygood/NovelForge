"""节点状态流转与 revision 规则（V4-04 §10–§11）。

```text
proposed → draft / superseded
draft    → accepted / superseded
accepted → superseded
superseded → （终态）
```

规则：

```text
· AI 新生成内容不能静默覆盖 accepted node；任何重新生成都产生新 revision
· accepted 节点被重新生成后，旧 revision 保持 accepted（历史），新 revision 为 proposal/draft
```
"""

from __future__ import annotations

from typing import Mapping

from .contracts import BlueprintNode
from .errors import BlueprintStatusError

ALLOWED_STATUS_TRANSITIONS: Mapping[str, tuple[str, ...]] = {
    "proposed": ("draft", "accepted", "superseded"),
    "draft": ("accepted", "superseded"),
    "accepted": ("superseded",),
    "superseded": (),
}

#: 需要作者确认才能进入的状态（V4-04 只记录，不实现审批 UI）
AUTHOR_CONFIRMED_STATUSES = ("accepted",)


def next_status_for_regeneration(current_status: str) -> str:
    """重新生成时新 revision 的状态：accepted 节点不降级，其历史保持 accepted。"""

    if current_status == "superseded":
        return "proposed"
    return "proposed"


def assert_can_regenerate(node: BlueprintNode | None) -> None:
    if node is None:
        return
    if node.status not in ("proposed", "draft", "accepted"):
        raise BlueprintStatusError(
            f"节点状态不允许重新生成：{node.status}",
            details={"node_id": node.node_id, "status": node.status})


__all__ = ["ALLOWED_STATUS_TRANSITIONS", "AUTHOR_CONFIRMED_STATUSES",
           "assert_can_regenerate", "next_status_for_regeneration"]

