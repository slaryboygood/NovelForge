# NovelForge 运行时工作区

`novel/runtime/` 用来保存每章独立的外部运行时工作区，例如 DeepSeek Harness。

推荐结构：

```text
novel/runtime/chapter_0001/
  planner/
  writer/
  reviewers/
  rewriter/
  state_extractor/
```

规则：

- NovelForge 负责 schema、上下文隔离、评审门禁、状态提交和回滚。
- Runtime provider 只执行模型任务，并返回文本或通过 schema 校验的 JSON。
- `skills_manifest.json` 只引用既有 `codex-skills/` 目录；不要复制或 fork skill。
- Writer 和 Rewriter 工作区不得包含 restricted author intent、endgame 文件或 restricted secrets。
- Reviewer 工作区可以接收 `input/review_only/` 文件，用于审计泄漏和 canon 冲突，但 Reviewer 仍不能改正文。
- Trace 文件只保存 hash 和进程元数据，不保存 API Key。
