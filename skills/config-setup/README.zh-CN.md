# config-setup

通过 CLI 配置插件的非密钥设置，并在全新安装时初始化 `config.yml`——这样无需手写 YAML，
直接对话即可完成设置。

- **首次配置** —— `scholar-workflow config init` 创建最小 `config.yml`，并写入你指定的
  `KEY=VALUE` 附加项。只写你设置的内容，不会倾倒全部默认值；若已存在内容不同的文件则拒绝覆盖。
- **旧配置迁移候选** —— 仅当旧投影命令仍需单一 Vault 时添加
  `--research-vault-root PATH`；动态 Source 与 Field 使用独立的 `knowledge` CLI，
  不需要 Hub。先预览、审阅单个 Field 方案，再用当前确认摘要登记；
  详见[知识目录登记](../../references/knowledge-registration.md)。
  真正的新 Source 会明确初始化空资源清单；挂接已有 Source 不会把丢失的清单当空库。
  创建中断后，用原登记命令与已审阅摘要恢复。
  schema 2 的领域引用复用既有对象，不创建第二份归属或副本。
  `knowledge list --resolve-references` 可选核验其声明归属和文件状态，阅读器仍未核验；
  开发树中的 `knowledge reference-plan/reference` 可预览并确认单条引用增删，
  只改引用方清单，不改目标内容；尚未随正常安装的 0.42.0 发布。
- **修改某项** —— `scholar-workflow config set KEY VALUE` 设置单个点分键
  （如 `notion.enabled`、`link_service.port`），并保留文件中的注释。
- **查看** —— `config show`（生效值）、`config show --raw`（文件原文）、
  `config get KEY`、`config path`。

`config.yml` 是非密钥配置的唯一权威。密钥（token、cookie、API key、密码）绝不写入其中——
请设为环境变量（Notion token 为 `SCHOLAR_WORKFLOW_NOTION_TOKEN`）；CLI 会拒绝疑似密钥的键。
recommend-papers 功能有独立的 `recommend.yml`，不在本 skill 范围内。

完整流程与约束见 [SKILL.md](./SKILL.md)。
