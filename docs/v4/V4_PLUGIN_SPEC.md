# NovelForge V4 — Plugin Spec（设计稿）

> 状态：**V4-00 Architecture / Proposed — 只定义，不实现**
> 依据：`docs/v4/V4_ARCHITECTURE.md` §4.1（`plugins.*` 行）、§5（Plugin 边界）
> 硬禁止：**Plugin 不允许直接任意修改核心数据库 / 文件系统。**

---

## 1. 先回答「为什么需要插件」

### 1.1 当前代码事实

V3 **已经有**三种事实上的扩展点，但都是「改核心代码 / 配置」而不是插件：

| 扩展需求 | V3 现状 | 是否已经是扩展机制 |
| --- | --- | --- |
| 新题材 | `novel/config/story_engine/*.json`（Genre Template）+ `*_pack.json`（ContentPack） | ✅ 数据驱动，无需改引擎（有源码守卫 `tests/test_story_engine_templates.py`） |
| 新设计步骤 / 目录 | `novel/config/story_builder/step_catalogs.yaml` | ✅ 数据驱动 |
| 新导出格式 | 无（`export_package.serialize_export` 只有 json / markdown / docx 三个分支） | ❌ 必须改核心代码 |
| 新质量规则 | 无统一位置（散落在 9 处 validator） | ❌ 必须改核心代码 |
| 新模型 provider | 无（`spec/llm.py` 单实现） | ❌ 必须改核心代码 |
| 新生成器 / 评估器 | 无 | ❌ 必须改核心代码 |

结论：**插件机制的真实需求集中在「导出 / 质量规则 / provider / 生成器」四类**，
题材与目录已经由数据驱动解决。

### 1.2 因此本文的立场

```text
不机械实现 Master Plan 的 8 种 Plugin 类型。
V4-09 先实现最小可用集合（3 类），其余标记为 Deferred（见 §3.2）。
```

这与 `V4_ARCHITECTURE.md` §3.2「暂时不建的抽象」一致：没有第二个使用者之前不建市场机制。

---

## 2. 通用 Plugin 契约

```python
class PluginManifest:
    plugin_id: str                  # 例如 "exporter.epub"
    version: str                    # 语义化版本 "1.2.0"
    plugin_api_version: int         # 宿主 API 版本（当前 1）
    kind: PluginKind                # 见 §3
    capabilities: list[str]         # 声明式 capability，见 §5
    required_permissions: list[str] # 见 §5.2
    entrypoint: str                 # "module:Class"
    config_schema: dict             # 配置的 JSON Schema
    min_novelforge_version: str
    max_novelforge_version: str | None

class PluginBase:
    manifest: PluginManifest

    def activate(self, host: PluginHost) -> None: ...   # 注册能力
    def deactivate(self) -> None: ...                   # 释放资源（幂等）
    def health(self) -> PluginHealth: ...               # 可选自检
```

### 2.1 PluginHost：插件唯一允许的对外通道

```python
class PluginHost:
    # 只读能力
    def read_resource(self, ref: str) -> ResourceView: ...
    def call_service(self, service: str, method: str, payload: dict) -> dict: ...

    # 注册能力
    def register_exporter(self, fmt: str, fn: Callable) -> None: ...
    def register_evaluator(self, gate: str, fn: Callable) -> None: ...
    def register_provider(self, provider_id: str, factory: Callable) -> None: ...

    # 受控写入（走 service，走 revision 协议）
    def propose(self, kind: str, payload: dict) -> ProposalRef: ...

    # 配置与日志
    def config(self) -> Mapping[str, Any]: ...
    def logger(self) -> Logger: ...
```

**没有** `db()`、`cursor()`、`open_file()`、`write_file()`、`gateway_override()`。

---

## 3. Plugin 类型

### 3.1 V4-09 必须实现（3 类）

| 类型 | 职责 | 输入 | 输出 | 允许的写入 |
| --- | --- | --- | --- | --- |
| `ExporterPlugin` | 新导出格式（EPUB / YAML / nfpack 变体） | `ExportView`（只读投影，由 ExportService 提供） | bytes + manifest | 无（导出物由 ExportService 落盘） |
| `EvaluatorPlugin` | 注册新质量规则到某个 Gate | `QualityScope` + `ContextView` | `list[QualityIssue]` | 无（issue 由 QualityService 收集） |
| `ModelProviderPlugin` | 新模型 provider | `LLMRequest`（messages / model / params） | `LLMResponse` | 无 |

### 3.2 Deferred（V4-09 不实现，需明确需求后再评估）

| 类型 | 为什么先不做 | 何时重启 |
| --- | --- | --- |
| `GeneratorPlugin` | 生成器与 `generation/*` 契约、LLM Contract 强耦合；在契约稳定前开放会让插件绕过质量门 | V4-05 质量循环稳定后 |
| `RepairPlugin` | 修复涉及 preserve / allow_change 边界，属于最高风险能力 | 至少一个完整 repair 周期上线后 |
| `GenrePlugin` | **已由数据满足**（Genre Template + ContentPack + `step_catalogs.yaml`） | 出现「题材自带代码逻辑」的真实案例时 |
| `ContextProviderPlugin` | 上下文装配是 memory 层核心，开放后难以保证预算与去重 | memory 层稳定后 |
| `MemoryPlugin` | 记忆是派生层且必须可重建，第三方写入会破坏该不变量 | 出现第二个真实需求时 |

### 3.3 每个 Plugin 能做什么 / 不能做什么（统一回答）

```text
能做：
  · 通过 PluginHost 只读访问资源与服务
  · 注册自己声明的 capability（导出格式 / Gate 规则 / provider）
  · 通过 propose() 产生 proposal（仍需作者或质量流程确认）
  · 读取自己的配置、写自己的日志

不能做：
  · 直接读写核心数据库 / 文件系统
  · 直接调用 LLM provider（必须经 ai.gateway）
  · 修改 StoryState / Canon
  · 修改 frozen 历史证据（workspace/wasteland_001_exports/**）
  · 注册未声明的 capability
  · 覆盖或修改其他插件的配置
  · 改变 Quality Gate 的 severity 或放行规则（只能新增规则，不能改门禁）
```

---

## 4. 注册、生命周期、配置

### 4.1 注册

```text
声明位置：novel/config/plugins/<plugin_id>/plugin.json      （每个插件一个目录）
发现顺序：内置 builtin → 配置目录（按 plugin_id 排序，保证确定性）
注册阶段：宿主启动时（不在请求路径上动态加载）
冲突规则：
  同名 capability 已注册 → 拒绝注册并记录（不静默覆盖）
  plugin_api_version 不兼容 → 拒绝加载，登记到 diagnostics
```

### 4.2 生命周期

```text
discovered → validated → activated → running → deactivated → unloaded

validated   : manifest 校验 + 版本兼容 + 权限声明检查 + capability 白名单检查
activated   : 调用 activate(host)，插件注册 capability
running     : 宿主调用其注册的 fn（每次调用在受控上下文内，带超时）
deactivated : 调用 deactivate()（幂等）；失败只记录，不阻塞宿主关闭
unloaded    : 释放引用；期间产生的临时文件必须清理
```

### 4.3 配置

```text
配置位置：novel/config/plugins/<plugin_id>/config.json（允许本地覆盖，gitignored）
校验：用 manifest.config_schema 严格校验
作用域：仅插件自身；不得读取其他插件或核心配置
敏感值：config 中不允许放 api key（由宿主提供，插件通过 host.secret(name) 获取）
```

---

## 5. Capability 声明与权限控制

### 5.1 Capability 白名单（V4 固定集合）

```text
export.format.<fmt>          ExporterPlugin
quality.gate.<Qn>            EvaluatorPlugin
model.provider.<id>          ModelProviderPlugin

（Deferred）
generation.task.<task>
repair.strategy.<name>
context.provider.<name>
memory.writer.<name>
genre.<genre_id>
```

### 5.2 权限模型

| permission | 含义 | 授予条件 |
| --- | --- | --- |
| `resource.read` | 只读访问资源 | 默认授予 |
| `service.call:<name>` | 调用指定 service 的只读方法 | manifest 声明 + 白名单 |
| `propose.write` | 产生 proposal | 需作者启用 |
| `export.emit` | 由 ExportService 落盘导出物 | 需作者启用 |
| `network.outbound` | 出网（provider 类必需） | 需作者显式启用 + 域名在 manifest 声明 |
| `secret.read:<name>` | 读取指定环境密钥名 | 需作者显式启用 |

```text
默认权限 = resource.read（最小权限）
任何需要写 / 出网 / 读密钥的插件，作者必须在启用时显式确认
```

---

## 6. 升级与版本不兼容

```text
plugin_api_version
  宿主 API 大版本变化 → 不兼容插件拒绝加载（不静默降级）

语义化版本
  manifest.min_novelforge_version / max_novelforge_version + version
  不满足 → 拒绝加载并登记 diagnostics（作者可见）

数据兼容
  插件自己产生的 artifact 必须带 plugin_id + version + api_version
  升级后若无法读取旧 artifact → 插件负责迁移或显式报错（不得静默丢弃）

卸载
  插件产生的导出物 / 报告保留（只读）
  插件注册的 capability 立即失效；已有 issue 保留并标记 rule_unavailable
```

---

## 7. 安全边界（正式条文）

```text
P1  Plugin → 不允许直接修改核心数据库（Canon sqlite / StoryState 文件 / 任何 truth 文件）
P2  Plugin → 不允许绕过 application.services 读写业务对象
P3  Plugin → 不允许修改 frozen 历史证据
P4  Plugin → 不允许改变 Quality Gate 的 severity 与放行规则
P5  Plugin → 不允许静默覆盖其他插件或内置能力
P6  Plugin → 故障必须隔离（异常 / 超时不得影响宿主主流程）
P7  Plugin → 卸载后宿主必须仍能正常工作（无残留注册、无残留文件锁）
```

实现建议（V4-09）：与 `V4_ARCHITECTURE.md` §4.2 的依赖矩阵一致 ——
只传 host 对象、不传 repository，从结构上保证 P1 / P2，而不是只靠代码评审。

---

## 8. 与 MCP 的区别（避免混淆）

| | Plugin | MCP |
| --- | --- | --- |
| 位置 | NovelForge **内部**扩展 | NovelForge **外部**协议入口 |
| 调用方 | 宿主自身（service 调用插件） | Agent / 外部工具 |
| 能力来源 | 宿主授予的 capability | 宿主暴露的 tool / resource |
| 风险形态 | 进程内代码（可读宿主对象） | 协议外调用（权限可显式拒绝） |

常见错误是把 MCP server 当插件装进 NovelForge，或用插件机制实现 MCP。
V4 明确：**MCP 是接口层，插件是能力层**，两者不共用注册机制。

---

## 9. 验收判据（V4-09）

```text
[ ] 存在 PluginManifest + PluginHost + registry + loader
[ ] 插件无法获得 repository / 文件句柄（结构性保证，可测试断言 host 无 db() 等方法）
[ ] 未声明的 capability 无法注册（测试）
[ ] 版本不兼容插件被拒绝加载并登记 diagnostics（测试）
[ ] 插件异常 / 超时不影响主流程（测试）
[ ] 卸载后宿主功能不变（测试）
[ ] ExporterPlugin 能产出新格式，且导出物带 revision / source_ids
[ ] EvaluatorPlugin 能产生 QualityIssue，但无法改变 severity 与放行规则（测试）
[ ] 至少一个 builtin 示例插件（建议 exporter.markdown.v2 或 evaluator.repetition）
```

