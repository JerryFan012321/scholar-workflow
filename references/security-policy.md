# 安全策略

## Zotero Bridge

- 仅监听 `127.0.0.1`
- 使用随机 token，放在请求头（`X-Scholar-Token`），不放在 URL
- 所有写请求要求 `Idempotency-Key` 请求头
- 只允许 `papers_root` 和受控临时目录中的规范化路径
- 拒绝 `..`、符号链接越界、超大请求（>50MB）、非 PDF 附件
- 限制 `Origin` 和 `Content-Type`，防止网页构造 POST 触发写入
- 不直接写 SQLite；只调用 Zotero JavaScript API 并使用事务保存
- Bridge 接口白名单：`health` / `collections` / `items/{key}` / `papers/upsert` / `attachments/link` / `items/update-metadata`
- 禁止：`eval_javascript` / `execute_sql` / `execute_shell` / 任意路径操作

## 本地链接服务

- 仅监听 `127.0.0.1:23128`
- 只接受不透明 Resource ID，不接受任意文件路径
- 最终文件必须位于 `papers_root` 或 `vault_root` 内
- 不提供任意 shell 执行能力

## 日志约定

- 日志不得记录 token、论文全文或用户的敏感绝对路径
- 只记录规范化相对路径和资源 ID

## Claude 权限边界

- 读取本地索引、状态、Zotero Local API：允许
- 用户明确要求的网络检索：允许
- 从 arXiv 下载 PDF：必须先展示计划并批准
- 写 Zotero / 移动 PDF / 写 Vault / 写 Notion：必须先展示计划并批准
- 删除、覆盖冲突、合并条目：禁止自动执行，逐项批准
- 直接写 Zotero SQLite：永久禁止
