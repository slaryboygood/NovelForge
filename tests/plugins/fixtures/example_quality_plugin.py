"""测试用 quality evaluator 插件（V4-09 §68、§96）：只依赖 plugin SDK。

规则（只读、确定性、"作者自定义规范"）：

```text
chapter 必须声明 pov（叙事视角）
```

Core 的 Q0–Q9 evaluator 只检查已填写的文本字段，不要求 pov 非空，
因此这条 issue 完全来自插件，
便于验证 namespaced code / provenance / non-blocking 默认策略。
"""

from novelforge.plugins import sdk

PLUGIN_ID = "com.example.qualitycheck"

ISSUE_CODE_SUFFIX = "CHAPTER_MISSING_POV"


def evaluate(context):
    """检查 chapter 是否声明叙事视角（只读，返回结构化 issue）。"""

    code = f"plugin.{PLUGIN_ID}.{ISSUE_CODE_SUFFIX}"
    rows = []
    for node in context.scoped() if hasattr(context, "scoped") else []:
        if node.node_type != "chapter":
            continue
        payload = context.payload(node)
        if str(payload.get("pov") or "").strip():
            continue
        rows.append(sdk.quality_issue(
            context, code=code, node_ids=(node.node_id,), severity="minor",
            reason="插件规则：章节未声明叙事视角（pov）",
            explanation="pov 为空（作者自定义规范）",
            metric={"pov_length": 0}))
    return rows


def register(context):
    return [sdk.quality_contribution(
        evaluator_id="title-lower-bound", gate="Q8", factory=evaluate, version=1,
        supported_node_types=("chapter",),
        issue_codes=(ISSUE_CODE_SUFFIX,),
        description="示例：章节标题长度下限检查")]


__all__ = ["ISSUE_CODE_SUFFIX", "PLUGIN_ID", "evaluate", "register"]
