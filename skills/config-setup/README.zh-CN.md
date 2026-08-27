# config-setup

通过 CLI 配置插件的非密钥设置，并在全新安装时初始化 `config.yml`——这样无需手写 YAML，
直接对话即可完成设置。

- **首次配置** —— `scholar-workflow config init --research-vault-root PATH` 创建
  `config.yml`，写入知识库路径以及你指定的 `KEY=VALUE` 附加项。只写你设置的内容，
  不会倾倒全部默认值；若已存在内容不同的文件则拒绝覆盖。
- **修改某项** —— `scholar-workflow config set KEY VALUE` 设置单个点分键
  （如 `notion.enabled`、`link_service.port`），并保留文件中的注释。
- **查看** —— `config show`（生效值）、`config show --raw`（文件原文）、
  `config get KEY`、`config path`。

`config.yml` 是非密钥配置的唯一权威。密钥（token、cookie、API key、密码）绝不写入其中——
请设为环境变量（Notion token 为 `SCHOLAR_WORKFLOW_NOTION_TOKEN`）；CLI 会拒绝疑似密钥的键。
recommend-papers 功能有独立的 `recommend.yml`，不在本 skill 范围内。

完整流程与约束见 [SKILL.md](./SKILL.md)。
