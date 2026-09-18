# ADR-026 — NovelForge Package Is A Selected Artifact, Not A Repository Backup

```
Status    : Accepted（V4-07 实施完成）
Date      : 2026-09-18
Context   : V4-07 Delivery, Export & NovelForge Package
Related   : ADR-007（artifact ownership）；ADR-024（revision pinned）；
            V4_DELIVERY_CONTRACT.md §9–§12
```

## Context

"打包导出"最常见的实现是把工作目录 zip 一下：

```text
zip -r export.zip novel/ workspace/ .env
```

后果：泄漏 provider secret、夹带其他作品、包含 cache / logs、把派生数据当事实传播，
而且交付物无法解释"里面为什么有这些文件"。

## Decision

1. **NovelForge Package（`.nfpack`）只包含明确选择的内容**：

   ```text
   manifest.json / blueprint/ / quality/ / revisions/ / provenance/ / editor/ / exports/
   ```

   目录结构与 profile / selection 决定（`package_includes_node_files` 控制是否带 node 原始文件）。
2. **不打包**：`.env` / API key / Authorization / provider secret / 完整 prompt /
   raw provider response / cache / logs / workspace / 其他作品 / 运行数据（§38、§71）。
3. **条目名安全**：拒绝 `../`、绝对路径、盘符、`~`、`.env`、`secret` 等（§70）。
4. **可验证**：manifest 记录每个 artifact 的 `path / mime_type / sha256 / size` 与
   exporter id+version（§39–§43）。
5. **机械测试**：扫描 package 内全部文本，确认没有其他作品的唯一标记（§72）。

## Consequences

正面：

* 交付物可以安全地交给外部（人 / Agent / 工具）而不泄漏内部状态；
* 交付物自包含可解释信息（manifest / snapshot / provenance）但**不是**仓库备份；
* 未来 MCP / Plugin 可以信任 package 结构与 checksum。

代价：

* 需要显式维护白名单式条目构造（不能偷懒 zip 目录）；
* 想要"完整归档"时不能复用本 package，需要独立备份机制（明确区分）。

## Alternatives considered

| 方案 | 为什么不选 |
| --- | --- |
| zip 工作目录 | 泄漏 secret、夹带其他作品、包含派生与缓存 |
| 只导出单文件 JSON | 无法承载 manifest / snapshot / 人类可读导出物 |
| 含全部 revision 历史 | 体积与隐私成本高且不属于交付；audit profile 才按需包含 |

## Evidence

```text
src/novelforge/delivery/exporters/package_exporter.py  entries / _entry_name / scan_for_secrets
src/novelforge/delivery/service.py                     secret 扫描失败即 blocked
tests/delivery/test_package.py                         结构、checksum、no-secrets、no-other-novel、路径安全
tests/delivery/test_delivery_service.py                原子发布与隔离
```

