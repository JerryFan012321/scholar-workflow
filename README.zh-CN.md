# scholar-workflow

面向 Claude Code 的学术资源管理插件。发现并导入论文、保持 Obsidian 索引与 Notion 投影
同步、构建文献 novelty tree、从四个源推荐每日论文、撰写论文详细分析 —— 由确定性 CLI 承担
可测试、可恢复的执行,Claude 负责理解、推荐与判断。

[English](./README.md)

## 架构

Claude 负责理解、分类与推荐;确定性 CLI(`src/scholar_workflow/`)负责可测试、可恢复的
文件操作,**从不发起网络调用、也不直接操作你的库**。**Zotero 是权威主库** —— 元数据、
存在性核验、语义检索一律经 [zotero-mcp](https://github.com/54yyyu/zotero-mcp)。新增性
写入(create / import / 元数据)经 zotero-mcp 的受控工具执行,破坏性动作需你批准。批准
后的论文 PDF 下载到收件箱,由你导入。**Obsidian** 保存知识笔记与派生索引;**Notion** 保存
可选的跨设备投影。

## Skills

| Skill | 用途 |
|---|---|
| find-resource | 搜索论文、核验身份、定位已有资源 |
| ingest-resource | 导入论文 / 归档技术文档 |
| sync-projections | 重建 Obsidian 索引表 + 同步 Notion 投影 |
| build-literature-tree | 构建 novelty tree(里程碑任务 → pipeline → 论文)+ flat 全集清单 |
| check-consistency | 跨系统一致性审计(只读) |
| export-annotations | 把某篇论文的 Zotero 批注整理成结构化 vault 笔记 |
| recommend-papers | 每日多源论文 feed + NotebookLM 略读 → 推荐清单 |
| analyze-paper | 论文详细分析,写成 vault 附属笔记 |
| env-setup | 搭建个人 API-key / SSH 服务器 env-records 台账 |

## 环境要求

- **Claude Code**(本项目是它的插件)。
- **Python ≥ 3.11** —— 确定性 CLI 是一个 Python 包。
- **Zotero + [zotero-mcp](https://github.com/54yyyu/zotero-mcp)** —— 权威主库。插件硬
  依赖它做读/写/语义检索;缺失时涉库 skill 会 fail-fast。
- **按功能可选:**
  - Notion 集成 token —— 仅启用 Notion 投影时需要。
  - `notebooklm-py` + Google 登录 —— 仅 `recommend-papers` 略读级 + 文献树 NotebookLM
    批读需要。
  - Scholar Inbox 账号 —— 仅该推荐源需要。

## 安装

1. **装插件。** 把本仓库作为 Claude Code 插件添加(经插件市场,或让 Claude Code 指向
   本地 clone / 仓库 URL)。

2. **装 CLI**(提供 skill 调用的 `scholar-workflow` 命令):
   ```bash
   pip install -e .        # 从 clone 安装
   # 或:pipx install scholar-workflow
   ```
   验证:`scholar-workflow --help`。

3. **建配置** `~/.config/scholar-workflow/config.yml`:
   ```yaml
   research_vault_root: ~/path/to/obsidian/vault  # 必填
   paper_inbox: ~/path/to/download/inbox          # 可选
   # notion: { enabled: true, ... }             # 可选,详见文档
   ```
   需要时用 `SCHOLAR_WORKFLOW_HOME` 覆盖配置目录位置。

4. **按需提供凭证**(见[环境要求](#环境要求))。token / cookie 存环境变量或各工具自己的
   登录态,**绝不进配置或 git**。如 Notion:`export SCHOLAR_WORKFLOW_NOTION_TOKEN=...`。

## 更新

插件版本记于 `.claude-plugin/plugin.json`(改动见 [CHANGELOG.md](./CHANGELOG.md))。拉取
最新 `release` 分支,若 CLI 版本有变则重跑 `pip install -e .`(或 `pipx upgrade
scholar-workflow`)。你的 `config.yml` 与凭证在仓库之外,更新不受影响。

## 使用

直接用自然语言跟 Claude Code 说,每个 skill 按意图触发,例如:

- *"找 DreamerV3 这篇论文并导入"* → find-resource → ingest-resource
- *"推荐今天世界模型方向的论文"* → recommend-papers
- *"分析这篇论文的方法部分"* → analyze-paper
- *"画一棵从 NeRF 到 3DGS 的文献树"* → build-literature-tree
- *"导出我对这篇论文的批注"* → export-annotations
- *"同步 Obsidian 索引和 Notion"* → sync-projections

各 skill 自己的 `README`(在 `skills/<名>/` 下)详述其选项与配置。推荐清单是临时的;你
留下的论文走常规 find/ingest 管线,不经判重不入库。

## 开发

这是 `release` 分支(仅运行时)。开发内容 —— 规范、规划文档、测试、评估 —— 在 `main`
分支,贡献指南见其 `AGENT.md`。测试在那边跑:`pytest tests/unit tests/contract`。
