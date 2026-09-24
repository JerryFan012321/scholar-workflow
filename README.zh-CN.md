# scholar-workflow

面向 Claude Code 与 Codex 的学术资源管理插件。它把人类优先的知识系统、可复现实验项目档案和
本机 typed Hub 控制面组合在一起：发现并导入论文、维护 Obsidian/Notion 投影、构建文献树、推荐
论文、生成经校验的 Markdown/Canvas 分析、初始化 Git 项目，并在多个 agent 运行时之间协调有界任务。

[English](./README.md)

## 架构

宿主 LLM 负责理解、分类、排序与推荐;确定性 CLI(`src/scholar_workflow/`)负责可测试的文件和
Zotero 操作。Zotero 适配器只连接 Zotero 10+ 的回环 Local API;其他对外访问均受限且显式声明——
`apply` 从 arXiv 下载 PDF,独立的 `bin/notion-project.py` / `bin/recommend-papers.py` 各自访问其
声明的服务。**Zotero 是权威主库** —— 元数据、存在性核验、索引全文与新增性写入使用官方
Local API。主题召回由 Local API 全字段/全文 quicksearch 加宿主模型排序完成,不需要 MCP server
或本地向量库。破坏性动作仍需批准。**Obsidian** 保存知识笔记与派生索引;**Notion** 保存可选投影。

### 三系统边界

- **Knowledge System** 以人类可读 Markdown 为正文。论文、重要技术文档和 Blog 是原子资源；
  分析、Canvas 和附件是显式归属的附属产物。全文分析固定覆盖任务、输入、分步流程、输出和边界，
  Evidence 与对应论点放在一起。
- **Project System** 保存稳定 `project_id`、宿主中立的源码/config profile，以及彼此分离的
  Run、Attempt、Target、成果 promotion 和备份记录。没有独立校验过的第二份副本就不能称为备份完成。
- **Hub Control Plane v3** 只提供一个 `HubDirectory` 根。文档 Libraries 只含 Zotero Papers 与
  动态 Obsidian Fields；Projects、Tools 与 Libraries 平级。cmux 只路由浏览器/终端窗口，登记的
  文件夹和项目独立决定文件/cwd 权限；Zotero、Field manifest、项目 manifest、显式 registry 与
  Codex 仍分别持有权威状态。

知识文档与项目文档之间只能显式复制。副本移除源系统的 `sw_*` 托管身份，获得目标系统身份后独立
演化；系统不建立隐藏同步或托管 provenance 关系。

### 本地研究 Hub

正常使用只需一个命令：

```bash
scholar-workflow open-hub
```

`open-hub` 会核验已安装构建、启动或安全重启 Scholar Workflow 自己管理的回环服务、发现动态端口并
打开 Hub。它不需要源码 checkout、`CODE_REPO_ROOT`、固定端口、nonce 或 lease。在 cmux 内运行时，
当前 workspace 会成为该页面的“默认打开位置”；在 cmux 外运行仍可阅读和执行独立授权的文件操作，
只有需要 cmux 的动作会提示选择目的地。

服务生命周期命令完整且幂等：

```bash
scholar-workflow hub start
scholar-workflow hub status
scholar-workflow hub restart
scholar-workflow hub doctor
scholar-workflow hub stop
```

`status` 显示真实 executable、插件/package/service build、协议、PID、动态端口、generation、启动时间
和日志位置。`stop` 只会停止 discovery 与在线身份握手共同证明属于 Scholar Workflow 的进程；未知
listener 不会被误杀。

页面结构是 `Libraries → Papers / Fields`，以及平级的 `Projects`、`Tools`。不再存在全局
“已绑定/只读”状态；Vault 写入、项目文档写入、cmux launch、Codex 任务、ZotFlow 批注和 Zotero Local API
分别报告能力。某个 cmux workspace 关闭时，只禁用路由到它的打开动作。

新增科研领域的具体步骤：

1. 打开 **Fields → 选择 Vault / 目录**。
2. 在系统文件选择器中选择一个 Obsidian Vault 或其子目录；浏览器不会收到绝对路径。
3. 查看零写入预览：候选 Field、入口文档、导航顺序、重名、模板改写、忽略文件、未映射正文和链接变化。
4. 只确认要初始化的 Field。一个 Source 可以包含多个 Field，每个 Field 自己定义导航分组。

如果所选 Vault 已有便携 Field manifest、但本机尚未登记，预览会改为**登记现有 Source**：明确列出
将出现的全部已有 Field 与身份；确认只登记本机位置，不修改 manifest 或原文档。

旧 `research_vault_root` 只作为迁移候选，不再是唯一必填知识库。Field 首页同屏显示 manifest 导航和
所选 Markdown 正文，不再经过文档落地页。

论文卡片直接执行动作：主按钮是**在 ZotFlow 标注**，次级动作包括在 Zotero 打开、在所选 cmux
workspace 阅读、系统阅读器、查看分析和打开批注笔记。ZotFlow 未安装、未启用或版本不兼容时，主动作
降级为 Zotero 并给出原因。Zotero 仍是批注唯一权威；只有 ZotFlow 可以在 Obsidian SecretStorage 中
持有 Zotero Web API 密钥，Scholar Workflow 只经 Local API 读取批注，绝不请求该密钥。旧
`/hub/item` 与 `/open/paper/...` 只保留一版兼容解析，正常 UI 不再产生它们。

Notion 等 Web 工具通过预登记 URL recipe 在所选 cmux browser surface 打开；CLI/Codex recipe 在那里
打开 terminal surface，但 cwd 只能来自登记的项目、Vault 或文件夹 Target。浏览器不能提交 URL、命令、
cwd、model、sandbox、permission、环境变量或原始 Codex 配置。项目文件操作仍只接受已注册
`project_id + docs 相对路径`，拒绝覆盖和 symlink 逃逸，删除进入可恢复 trash，Hub 不执行 Git 写入。

要在 Hub 中运行 Codex 任务，先在运行 Hub 的主机上登记一次可信工作目录，并配置本机 Codex：

```bash
scholar-workflow hub target list
scholar-workflow hub target add-source SOURCE_ID --target-id research
# 或使用已登记的项目：
scholar-workflow hub target add-project PROJECT_ID --target-id project
scholar-workflow hub codex configure --executable /absolute/path/to/codex --model YOUR_MODEL --sandbox workspace-write
scholar-workflow hub codex status
scholar-workflow hub restart
```

`SOURCE_ID` 会显示在 **Fields → 选择 Vault / 目录** 的预览中；`PROJECT_ID` 来自已登记项目的 manifest。
按实际工作对象选一种 Target 登记方式即可。`configure` 只探测显式指定的可执行文件，并把 model、
sandbox 保存在服务端策略；Hub 不扫描 `$PATH`。随后在页面的 **Codex 任务** 区选择任务、Target、
打开位置、思考强度，输入不超过 8 KiB 的任务说明，再启动。页面会显示运行状态和所选 cmux 终端。
配置、有效目的地或 worker 能力检查缺失时，会单独说明不可用原因。对于只需阅读的任务，管理员
也可以选择 `--sandbox read-only`。

要让其他 PDF 阅读器查看 Zotero 批注，可显式生成一份独立副本：

```bash
scholar-workflow zotero snapshot-annotations ATTACHMENT_KEY --output /path/to/annotated-copy.pdf
```

命令生成新 PDF 与哈希收据，不覆盖 Zotero 附件，也不把对副本的编辑同步回 Zotero；无法支持的
批注类型会明确报错。

明确登记 Field、并验收其精确迁移预览后，才逐 Field 清理旧论文链接：

```bash
scholar-workflow hub field-migration plan SOURCE_ID FIELD_ID
scholar-workflow hub field-migration apply SOURCE_ID FIELD_ID --approved-digest sha256:PLAN_DIGEST
```

`plan` 完全只读；每个不同的附件 key 都须通过 Zotero Local API 核实为个人库中可读取的 PDF，
才能批准稳定 URI。条目不存在、组库、非 PDF、不支持的附件形式或 Local API 不可用，都会成为
明确的计划冲突；`apply` 在创建恢复快照或写入前再次核验。`apply` 重新扫描并要求摘要与已验收
计划完全一致，只改 Field manifest 明列的 Markdown/Canvas。未映射文件若仍有旧链接会阻断。
此命令不重排论文分析，也不自动规范化 JEPA 模板。同步失败会回滚；若进程在多文件替换中崩溃，
须人工从 recovery snapshot 恢复，不能把它视为已验证备份。

完整运行期契约见 [`references/hub-contract.md`](references/hub-contract.md)。Field 迁移产生的 recovery
snapshot 不是 verified backup；真正备份仍需要独立介质和恢复演练。

## Skills

| Skill | 用途 |
|---|---|
| survey-topic | 界定开放式"调研 X"请求的范围,再路由到其他 skill |
| find-resource | 搜索论文、核验身份、定位已有资源 |
| ingest-resource | 导入论文 / 归档技术文档 |
| sync-projections | 重建 Obsidian 索引表 + 同步 Notion 投影 |
| build-literature-tree | 构建 novelty tree(里程碑任务 → pipeline → 论文)+ flat 全集清单 |
| check-consistency | 跨系统一致性审计(只读) |
| export-annotations | 把某篇论文的 Zotero 批注整理成结构化 vault 笔记 |
| recommend-papers | 每日多源论文 feed + NotebookLM 略读 → 推荐清单 |
| analyze-paper | 把论文详细分析投影为 Markdown + 可编辑 Canvas 文档对 |
| env-setup | 搭建并查阅个人 API-key / SSH 服务器 env-records 台账 |
| agent-collaboration | 在 Claude Code、Codex 或其他可用 agent 之间双向协调边界清楚的任务 |
| init-project | 初始化宿主中立、由 Git 管理且不带自定义 agent/hook 的研究项目骨架 |
| config-setup | 初始化、查询和更新插件配置 |
| project-backlog | 维护本仓库的持久化工作项队列 |

## 环境要求

- **Claude Code 或 Codex**(Codex CLI / Codex app;IDE extension 不加载插件)。
- **Python ≥ 3.11** —— 确定性 CLI 是一个 Python 包。
- **Git** —— `init-project` 创建或核验项目骨架时需要。
- **cmux** —— 只在需要把 Web/terminal/Codex/CLI 窗口路由到指定 workspace 时使用；它不授予
  文件权限，也不是阅读、Vault 保存或已登记项目文档操作的前置条件。
- **Zotero 10+ 且启用 Local API** —— 权威主库。在 Zotero 的
  **设置 → 高级**中启用;不再需要 Zotero 插件或 MCP server。Codex 在沙箱中运行时可能还需
  放行 localhost/网络权限才能访问 23119;在把 exit 3 判断为 Zotero 离线前,应带该权限重试。
- **按功能可选:**
  - **Obsidian + ZotFlow** —— 用于在 Obsidian 中标注 PDF。Hub 会检查 app/plugin 版本与 ZotFlow
    `minAppVersion`，不兼容时只报告，不自动升级 Obsidian。Zotero Web API 密钥只留在 Obsidian
    SecretStorage。
  - Notion 集成 token —— 仅启用 Notion 投影时需要。
  - `notebooklm-py` + Google 登录 —— 仅 `recommend-papers` 略读级 + 文献树 NotebookLM
    批读需要。
  - Scholar Inbox 账号 —— 仅该推荐源需要。
  - 目标 agent 的 CLI 与既有登录态 —— 仅 `agent-collaboration` 跨宿主运行时调用时需要;
    使用宿主原生 agent 工具时不需要。

## 安装

1. **在宿主中安装插件。**

   release 同时提供 Codex 原生 marketplace 元数据与 Claude 兼容 marketplace 入口；
   两者安装的是同一个插件根目录与同一版本。

   Claude Code:
   ```text
   /plugin marketplace add JerryFan012321/scholar-workflow@release
   /plugin install scholar-workflow@jerry-plugins
   ```

   Codex CLI:
   ```bash
   codex plugin marketplace add JerryFan012321/scholar-workflow --ref release
   codex plugin add scholar-workflow@jerry-plugins
   ```
   安装后新开 Claude Code 或 Codex 会话,让 bundled skills 与 hooks 生效。

2. **装 CLI**(提供 skill 调用的 `scholar-workflow` 命令):
   ```bash
   pip install -e .        # 从 clone 安装
   # 或:pipx install scholar-workflow
   ```
   验证:`scholar-workflow --help`。

3. **建配置。** 直接在对话中说「配置 scholar-workflow」,`config-setup`
   skill 会替你执行;或手动跑:
   ```bash
   scholar-workflow config init
   # 额外设置可内联 KEY=VALUE,如:
   #   scholar-workflow config init notion.enabled=true
   scholar-workflow config set paper_inbox ~/path/to/download/inbox   # 后续改单项
   scholar-workflow config show                                       # 查看生效值
   ```
   这会写 `~/.config/scholar-workflow/config.yml`(只写你指定的键,非全倒默认值)、校验、
   后续编辑时保留注释。需要时用 `SCHOLAR_WORKFLOW_HOME` 覆盖位置。每个 Vault/目录从
   **Hub → Fields → 选择 Vault / 目录**登记；旧 `research_vault_root` 只作为迁移候选。

4. **授权 Zotero 写入。** 启动 Zotero 后运行:
   ```bash
   scholar-workflow zotero probe
   scholar-workflow zotero authorize
   ```
   多阶段 PDF 导入请选择 Zotero 弹窗中的 **Always Allow**。密钥存入 macOS Keychain,
   不会打印或写进 config/git;读命令不需要密钥。

5. **按需提供其他凭证**(见[环境要求](#环境要求))。token / cookie 存环境变量或各工具自己的
   登录态,**绝不进配置或 git**。如 Notion:`export SCHOLAR_WORKFLOW_NOTION_TOKEN=...`。

## 更新

两个宿主 manifest(`.claude-plugin/plugin.json` 与 `.codex-plugin/plugin.json`)共用同一版本
(改动见 [CHANGELOG.md](./CHANGELOG.md))。刷新 marketplace 或拉取最新 `release` 分支,
若 CLI 版本有变则重跑 `pip install -e .`(或 `pipx upgrade
scholar-workflow`)。你的 `config.yml` 与凭证在仓库之外,更新不受影响。

## 使用

直接用自然语言跟 Claude Code 或 Codex 说,每个 skill 按意图触发;Codex 也可用
`$skill-name` 显式调用,例如:

- *"帮我调研一下世界模型这个方向"* → survey-topic →(推荐 / 查找 / 文献树…)
- *"找 DreamerV3 这篇论文并导入"* → find-resource → ingest-resource
- *"推荐今天世界模型方向的论文"* → recommend-papers
- *"分析这篇论文的方法部分"* → analyze-paper
- *"画一棵从 NeRF 到 3DGS 的文献树"* → build-literature-tree
- *"导出我对这篇论文的批注"* → export-annotations
- *"同步 Obsidian 索引和 Notion"* → sync-projections
- *"让 Claude Code 和 Codex 分工完成这次迁移并整合"* → agent-collaboration
- *"用标准骨架初始化这个项目"* → init-project

各 skill 自己的 `README`(在 `skills/<名>/` 下)详述其选项与配置。推荐清单是临时的;你
留下的论文走常规 find/ingest 管线,不经判重不入库。

## 状态与已知限制

插件仍处于 `0.x` 活跃开发期。哪些已稳、哪些仍在打磨:

- **Zotero 10.0.2 实机已跑通:** Local API 已完成 probe、search、collections、持久写授权、
  条目创建、imported PDF 上传、精确 DOI 复用与附件复用。同一 ingest payload 重跑会返回原
  item/attachment，不重复上传。
- **Hub v3 已取代 v0.28.1 binding 模型:** cmux 只表示打开位置，可信 folder/project Target 决定
  文件与 cwd；受管 lifecycle 使用动态端口和自证 discovery，不依赖固定 23128 或源码目录。
- **真实数据继续逐 Field 门禁:** 首个 Source 是当前科研技术文档 Vault，首个 Field 是世界模型，
  JEPA/V-JEPA 是验收样本。该 Field 必须先展示 preview 并获确认；其他 Vault/项目保持不动。
- **ZotFlow 兼容性只诊断、不自动修复:** 若当前 Obsidian 低于插件 `minAppVersion`，Hub 禁用动作并
  说明所需升级；不会自动升级 Obsidian 或卸载其他插件。
- **已实现但尚未真实端到端跑通:** `build-literature-tree` 的 CLI 渲染路径(尤其第四层
  `module` 和落盘到 vault 的挑战洞见树)、`recommend-papers` 的 NotebookLM 略读层、
  `check-consistency`。
- **不支持跨运行续跑:** 重跑 `apply` 是全新任务、会把每一项从头下载,不会接着上次的进度。
- **身份安全双层执行:** skill 先预览候选,`zotero ingest` 在创建前再次执行 DOI 或规范化
  title+creators 精确核验。当前 CLI 不暴露破坏性 Zotero 命令;未来若增加仍需审批。

## 开发

发布后的 `release` 分支仅包含运行时文件、Codex 原生及 Claude 兼容 marketplace 元数据与两个宿主
manifest。开发规范、规划文档、测试与评估在 `main` 分支；贡献指南见其 `AGENT.md`，测试在该分支运行
`pytest tests/unit tests/contract`。
