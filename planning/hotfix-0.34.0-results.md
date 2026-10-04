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

## 正常发布、安装与只读实机结果

- source `108658d2c0c9f5a14205bf0daad3b0c8c47b2935` 已推独立 hotfix；make-release 在干净临时克隆
  生成 runtime `7afea994bcb90e58a07240a2d934c2022fc85e89` 并推 release。根文件边界正确，
  grep 未发现个人路径、真实测试 library/attachment ID 或明显密钥。
- pipx 固定 runtime SHA 正常更新；direct_url commit/requested_revision 一致。CLI、模块、包元数据
  与两个 plugin manifest 均0.34.0。正常 marketplace upgrade/add 安装 cache 0.34.0，未手改缓存。
- 安装版公开 preview 的输入只为既有 V-JEPA2 候选的 `resources/papers/2025-v-jepa-2/`；
  Markdown/JSON 两次均 exit0。一个临时 Field，分析正文为已有入口，阅读说明进入导航；
  unmapped/conflicts/external writers/legacy changes 均为空。结论只适用于所选子目录。
- 执行前后 registry SHA256 `51dad852da65215021a6fed146486e226571b051313195b083eb01d1ad994b5f`、
  Markdown `f2f1c0df1eafc915ab2d2433bc70bab501d9a0c2a41e571ba94c4978ac2c7559`、
  Canvas `ae474839336040886b8b92e223d440c206627365eb24264de1046fcdd2fff4f1` 不变。
  所选目录未生成 fields.yml，临时候选身份和进程内 token 未被用于登记。
- 原始公开输出和独立中文说明保存于 test 的 `Scholar Workflow 实验/知识文件夹-0.34.0/`。
  首次打开因应用未及时索引返回 File not found；重新核对真实 Vault 根后，同一路径成功打开，
  app activeFile/root/exists 均吻合，五条资料 wikilink 实际解析到现有文件。
- Obsidian 阅读视图截图 `阅读视图.png` 已保存并查看，说明实际渲染；截图不代表人工评鉴通过。
  本轮使用 obsidian-markdown 保持薄 frontmatter、独立可读正文和原生资料链接，未引入机器身份注释。

预览只列 Markdown 导航，Canvas 由分析正文持有；展示链接不被维护成新权威关系。
新增能力不能代替完整模范 Source/Field：正式登记与 v5 文档的联合事务仍未完成，旧迁移路径
只接受 v4，下一切片须检查并适配该接口，不降级现有图、不重复生成当前 pair。
用户仍需评鉴说明是否清楚、入口是否好找；G17、科学来源和其他原生工具未全项完成，main 未合并。
