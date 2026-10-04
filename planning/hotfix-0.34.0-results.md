# 0.34.0：无 Hub 的知识文件夹预览

日期：2026-10-05。独立 hotfix，main 未合并；G17 未完成。

## 输入、范围与开发结果

独立方案：`knowledge-preview-test-plan.md`。公开 CLI 复用 knowledge.FieldService 与
现有 `hub/sources.json` 位置，不依赖 HTTP/进程/工作区，不改原登记/写入代码或论文渲染器。

- 首轮定向29通过（1.54s）。补 registry 身份/重叠负例后40通过、1失败（1.55s）：
  测试错误地期待已有 Source 没有新 Field 时无登记约束，实际 provider 必须拒绝再次初始化。
  保留原 provider 行为，只修正该独立预期，并把人类诊断标题改为“登记约束”。
- 修正后定向41通过（1.53s），含12个新增公开 CLI 契约、17个原 Field 契约、版本及 eval schema。
- 新 formatter/test 的 Ruff、原 analyze-paper skill validator、diff 空白检查通过。
  整个旧 cli.py 的四处 I001 在 HEAD 原文件也存在，未顺手重排历史 Hub 导入。
- 所有 routing 描述未改；新增 preview-only safety 与 outcome（pending）。不规定内部思考。

完整 unit/contract 回归1453通过、11既有警告（76.36s）。正常发布安装、真实单对象预览与可见展示结果待补充。
回退安装：0.33.0 runtime `3f00999797beab81c032775038917ff72ae5c480`。

本轮不创建新首页、登记 test Source/Field、迁移正式 Vault、生成 Canvas、改 Zotero/服务或真实项目。
