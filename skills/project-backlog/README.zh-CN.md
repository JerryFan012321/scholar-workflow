# project-backlog

项目待办队列管理 skill,维护 `planning/BACKLOG.md` 的持久化工作项清单。

## 用途

追踪其他地方没覆盖的具体待办、决策和阻塞项:
- GOALS.md 保存长期目标与不变量
- CHANGELOG.md 记录已发布的变更
- Git 显示已暂存/未暂存的改动
- 本 skill 填补空缺:**什么在等、什么需要决策、什么被阻塞、什么可以开工**

每个工作项有稳定 ID(`WI-NNN`)、状态(ready/pending-decision/blocked/in-progress/done/deferred)、优先级、上下文和下一步行动。

## 使用

用自然语言跟 Claude Code 或 Codex 说:

- *"加个待办:给导入文档增加 checksum 校验"* → 新建工作项并附上下文
- *"哪些需要我决策?"* → 列出所有 `status:pending-decision` 的项
- *"把 WI-003 标记为完成"* → 移到 Completed
- *"WI-005 被阻塞,等我决定作用域"* → 更新状态和阻塞原因
- *"待办概览"* / *"待办状态"* → 完整待办概览(汇总 + 分类列表)
- *"现在能做什么?"* → 状态为 `ready` 且无阻塞的项

## Schema

每个工作项包含:
- **ID**: `WI-NNN`(自增,永久稳定)
- **Title**: 单行摘要
- **Status**: ready | pending-decision | blocked | in-progress | done | deferred
- **Priority**: p0(紧急)| p1(高)| p2(中)| p3(低)
- **Type**: code-change | eval | decision | planning | documentation | refactor
- **Context**: 2-4 行说明为什么存在、影响什么
- **Blocker**: 在等什么(另一个 WI、用户决策、外部依赖,或"none")
- **Next action**: 怎样推进
- **Related**: 可选链接到 GOALS.md 的 ID、阶段文档、外部引用

## 文件位置

`planning/BACKLOG.md` — 唯一真相源,与 GOALS.md、HANDOFF.md 一起入库。

## 与其他项目产物的集成

- **GOALS.md** — 工作项可在 `Related` 字段引用目标 ID(G1、INV5、NG3)
- **CHANGELOG.md** — 工作项完成并发布时,变更记入 CHANGELOG;工作项本身移至 backlog 的 Completed
- **TaskCreate/TaskUpdate** — 那些是临时的、会话级的。实现步骤用它们;跨会话持久化用本 skill

## 示例工作项

```markdown
### WI-020: 给导入文档增加 checksum 校验
- **Status**: ready
- **Priority**: p1
- **Type**: code-change
- **Context**: 技术文档写入索引前需要稳定的内容完整性校验。
- **Blocker**: none
- **Next action**: 定义 checksum 字段、接入 ingest 路径并增加契约测试。
- **Related**: ingest-resource skill
```
