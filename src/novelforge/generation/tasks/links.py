"""Causal Link 与 Setup / Payoff 的结构化构建（V4-04 §26–§27）。

这两个能力**不需要**新的 LLM 调用：它们是从已生成的 Scene / Chapter Card 中
确定性提取的结构关系（因此天然可重建、可解释）。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from novelforge.blueprint import (
    CausalLinkPayload,
    PayoffPayload,
    SetupPayload,
)

#: 派生结构节点（setup / payoff）在同一父节点下的排序基准：
#: 它们排在叙事子节点（章节 / 场景）之后，避免与 sequence=1..N 冲突。
DERIVED_SEQUENCE_OFFSET = 1000


def build_causal_links(scenes: Sequence[Mapping[str, Any]], *,
                       novel_id: str) -> list[dict[str, Any]]:
    """按场景顺序建立因果链：上一场的 outcome 促成 / 触发下一场的冲突。

    规则（确定性、可解释）：

    ```text
    prev.outcome 存在 → (prev) --causes--> (next)
    next.payoff 非空   → (prev) --pays_off--> (next)
    prev.setup 非空    → (prev) --enables--> (next)
    next.turn == ""    → 不建立 motivates（信息不足，不猜）
    ```
    """

    rows: list[dict[str, Any]] = []
    ordered = [row for row in scenes if str(row.get("node_id") or "")]
    for index in range(len(ordered) - 1):
        prev, nxt = ordered[index], ordered[index + 1]
        prev_id = str(prev.get("node_id"))
        next_id = str(nxt.get("node_id"))
        if str(prev.get("outcome") or "").strip():
            rows.append({"source_node": prev_id, "target_node": next_id,
                         "relation": "causes",
                         "reason": f"{prev_id} 的结果改变了 {next_id} 的起点"})
        if list(nxt.get("payoff") or []):
            rows.append({"source_node": prev_id, "target_node": next_id,
                         "relation": "pays_off",
                         "reason": f"{next_id} 回收了此前埋设的 setup"})
        if list(prev.get("setup") or []):
            rows.append({"source_node": prev_id, "target_node": next_id,
                         "relation": "enables",
                         "reason": f"{prev_id} 埋设的 setup 为 {next_id} 提供条件"})
    return rows


def build_setups(scenes: Sequence[Mapping[str, Any]], chapters: Sequence[Mapping[str, Any]],
                 *, novel_id: str) -> list[dict[str, Any]]:
    """把 setup 文本提升为结构化 Setup 节点（同一文本只出现一次）。"""

    rows: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for owner in [*chapters, *scenes]:
        owner_id = str(owner.get("node_id") or "")
        for text in owner.get("setup") or []:
            content = str(text).strip()
            if not content or content in seen:
                continue
            setup_id = f"setup_{len(seen) + 1:03d}"
            seen[content] = setup_id
            rows.append({"setup_id": setup_id, "content": content,
                         "introduced_at": owner_id, "expected_payoff": "",
                         "status": "open",
                         "payload": SetupPayload(content=content, expected_payoff="",
                                                 status="open")})
    return rows


def build_payoffs(scenes: Sequence[Mapping[str, Any]], chapters: Sequence[Mapping[str, Any]],
                  setups: Sequence[Mapping[str, Any]], *, novel_id: str
                  ) -> list[dict[str, Any]]:
    """把 payoff 文本提升为结构化 Payoff，并尽量绑定对应 setup。"""

    by_content = {str(row["content"]).strip(): str(row["setup_id"]) for row in setups}
    rows: list[dict[str, Any]] = []
    index = 0
    for owner in [*chapters, *scenes]:
        owner_id = str(owner.get("node_id") or "")
        for text in owner.get("payoff") or []:
            content = str(text).strip()
            if not content:
                continue
            index += 1
            resolved = [by_content[content]] if content in by_content else []
            rows.append({"payoff_id": f"payoff_{index:03d}", "resolved_at": owner_id,
                         "result": content, "resolves_setup_ids": resolved,
                         "status": "planned",
                         "payload": PayoffPayload(resolves_setup_ids=resolved,
                                                  result=content, status="planned")})
    return rows


def apply_setup_payoff_status(setups: Iterable[Mapping[str, Any]],
                             payoffs: Iterable[Mapping[str, Any]]
                             ) -> list[dict[str, Any]]:
    """根据 payoff 绑定情况给出 setup 状态（open / partially_paid / paid）。"""

    counts: dict[str, int] = {}
    for payoff in payoffs:
        for setup_id in payoff.get("resolves_setup_ids") or []:
            counts[str(setup_id)] = counts.get(str(setup_id), 0) + 1
    rows: list[dict[str, Any]] = []
    for setup in setups:
        setup_id = str(setup["setup_id"])
        paid = counts.get(setup_id, 0)
        status = "paid" if paid >= 1 else "open"
        rows.append({**dict(setup), "status": status})
    return rows


def causal_link_node_id(index: int) -> str:
    return f"cl_{int(index):03d}"


__all__ = ["apply_setup_payoff_status", "build_causal_links", "build_payoffs",
           "build_setups", "causal_link_node_id"]
