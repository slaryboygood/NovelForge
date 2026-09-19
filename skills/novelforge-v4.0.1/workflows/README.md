# Module: `workflows` — 组合层（不是 product owner）

```text
Module purpose     把 atomic skill 串成端到端流程
Authoritative owner 无（组合层）；每个步骤的 owner 是它所属的 capability module
Owned skills       create-new-story-blueprint / review-and-repair-blueprint /
                   prepare-final-delivery / use-novelforge-through-mcp / operate-with-agent
Truth ownership    无。Workflow 不拥有能力、不复制步骤
Public interfaces  与所组合的 atomic skill 相同
Dependencies       全部 atomic 模块（只按 stable skill ID 引用）
Forbidden          复制 atomic skill 的 Procedure；把 workflow 当成 owner 写业务规则；
                   绕过 preconditions / approval / verification
Related modules    所有
```

## 写法规则（§48–§49）

```text
· Workflow 只写：Step N → skill ID（稳定 ID，不复制底层操作）
· Atomic skill 才是 SSOT；workflow 里出现"底层细节"就是复制，属缺陷
· Workflow 必须保留 approval 边界（accept / deliver 不得由 workflow 自动执行）
```
