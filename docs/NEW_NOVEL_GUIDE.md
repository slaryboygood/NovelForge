# 新建一本小说（T16-06）

## 在界面里

1. 打开 <http://127.0.0.1:8000/>（或你部署的地址）。
2. 空状态里填写「新小说编号」（如 `novel_xianxia`），在「内容包」里选择这套小说的运行内容（如修仙演示），点「新建小说」。
3. 页面切到这本小说，选择「新故事起点」（读者体验 / 世界观 / 人物灵感 / 开场事件），点「开始构筑」。
4. 走完十步设定，确认故事蓝图。
5. 点「开始 / 继续旅程」，按剧情提示做选择；到「本段旅程结束」后可「用当前路线整合大纲」。
6. 刷新页面会恢复当前小说、内容包、旅程进度与大纲。

## 用 API 建小说

```powershell
curl -X POST http://127.0.0.1:8000/api/story-builder/novels -H "Content-Type: application/json" `
  -d '{"novel_id":"novel_xianxia","title":"修仙示例","template_id":"xianxia","content_pack_id":"xianxia_demo"}'
```

- `template_id` 决定默认目录（可留空 = 自定义题材）。
- `content_pack_id` 决定旅程文本与行动；留空则使用默认包。
- 之后用 `POST /api/story-builder/sessions`（`project_id` = `novel_id`）创建故事。

## 边界提醒

- 新建小说与模板都只是配置：不会自动获得资源、能力或知识。
- 不同小说各自独立存储（会话、蓝图、大纲、StoryState、内容包互不影响）。
- 作者知道 ≠ 角色知道；未来规划 ≠ 已发生事实。

## 相关命令

```powershell
curl http://127.0.0.1:8000/api/story-builder/novels
curl http://127.0.0.1:8000/api/story-builder/content-packs
```
