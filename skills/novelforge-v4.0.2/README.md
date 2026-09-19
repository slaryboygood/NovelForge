# NovelForge V4.0.2 — 操作知识层（Skill Baseline，增量继承 V4.0.1）

> 这是 **V4.0.2 的版本化 Skill baseline**（`status: frozen-baseline`）。
> 它**继承** `skills/novelforge-v4.0.1/**`，只覆盖 V4.0.2 P0 Stabilization 真正改变的部分。
> V4.0.1 目录保持历史原样（它记录的缺陷在 V4.0.1 里是真实存在的）。

## 继承规则（唯一机制，不引入新框架）

```text
inheritance_mode: copy-and-override（继承 + 同路径覆盖）

1 生效集合 = V4.0.1 baseline 的所有文件
             ∪ 本目录的同路径覆盖（overrides）
2 覆盖必须是"同路径替换"：相对路径必须已存在于 V4.0.1，不允许随意新增 skill 目录
3 未被覆盖的 skill / module README / catalog / source map 一律继承 V4.0.1
4 哈希：SKILL_MANIFEST.json 同时记录
   · base：V4.0.1 的 SKILL_MANIFEST.json 路径（用于确认基线未被改动）
   · overrides：本目录文件的 sha256（与 V4.0.1 同规则：CRLF → LF 后哈希）
5 校验：python scripts/validate_v4_0_2_skills.py
```

### Skill ID 命名空间规则（简单、可审计）

```text
· 被覆盖（override）的文件 → 使用 `novelforge-v4.0.2.<module>.<skill>`（表示"本版本改过"）
· 未被覆盖的文件           → 保持 `novelforge-v4.0.1.<module>.<skill>`（它们就是 V4.0.1 的那份 skill）
· 因此 workflow 的 Step 列表里会同时出现两个前缀：这是有意设计 —— 一眼就能看出哪一步
  在本版本被修正过；不要为了一致性重写 77 个未变化的 skill。
```

## V4.0.2 相对 V4.0.1 的变化（只有这些）

| 路径 | 变化 | 为什么 |
| --- | --- | --- |
| `delivery/README.md` | issue 生命周期语义（live issue） | PB-1 修复 |
| `delivery/validate-delivery/SKILL.md` | 删除"历史 issue 永久阻塞 / 只能用 explicit_revisions 绕过"的临时警告 | PB-1 修复 |
| `agent/README.md` | approval 是 durable evidence | PB-2 修复 |
| `agent/approve-agent-run/SKILL.md` | 删除"approve 当前必然失败"的临时警告；写清批准后的状态机 | PB-2 修复 |
| `mcp/README.md` | stdio 入口在支持区间内可用 | PB-3 修复 |
| `mcp/start-mcp-server/SKILL.md` | 删除"stdio 启动即崩 / 用 in-process 兜底"的临时警告 | PB-3 修复 |
| `workflows/prepare-final-delivery/SKILL.md` | 记录默认 preflight 闭环实测 | PB-1 closure |
| `workflows/operate-with-agent/SKILL.md` | 记录 protected approval 闭环实测 | PB-2 closure |
| `workflows/use-novelforge-through-mcp/SKILL.md` | 记录 stdio + 真实资源读取闭环实测 | PB-3 closure |

## 使用纪律（与 V4.0.1 相同，继承）

```text
· 显式携带 novel_id；写操作带 expected_revision + idempotency_key
· 优先 UI / REST / Application / MCP；不直接编辑落盘 artifact
· AI 产出是 proposal；accept / reject / restore 属作者决定
· 质量通过 ≠ 作者已接受；交付默认 accepted + revision-pinned
· 不绕过 frozen 边界（Canon / StoryState / legacy 源 / frozen Repair Contract 与 Gate）
```

## 版本政策

```text
V4.0.2 是 bugfix 版本（PB-1 / PB-2 / PB-3），没有新增 major capability。
未来版本（V4.0.3 / V4.1 / V5）各自建立新的 baseline 并显式记录继承关系；
不要静默修改本目录。必须纠正文档错误时走 SKILL_BASELINE_UPDATE：
说明原因 → 更新 SKILL_MANIFEST.json 哈希 → 更新测试。
本 baseline 不是产品 tag：不要创建 skill 专用 Git tag，也不要移动 v4.0.1 / v4.0.0 / *-final。
```
