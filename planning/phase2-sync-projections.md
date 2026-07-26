# Phase 2 规格 — Obsidian 索引 + 本机 PDF 链接服务

> 规划层文档(永久,不归档)。意图对照 `GOALS.md`(G2/G5/G6,INV4/INV17/INV18),
> 变更史 `../CHANGELOG.md`。本轮 = Obsidian 索引 + 本机 PDF 链接服务;**Notion 押后**。

## 目标(本轮)

把已入库的论文(Zotero 权威)投影成 Obsidian 的可重建索引表,并让表里指向论文的
链接能在本机 cmux 浏览器里**一键内联看到原始 PDF**。

## 架构与数据流(可知性)

```
宿主 LLM ──调 zotero-mcp get_item_details──→ 取字段(title/authors/year/venue/DOI/arXiv/附件key)
    │ 格式化成 rows(JSON)
    ▼
CLI project-obsidian(读 JSON)──→ obsidian.py managed-block 正则精确替换 ──→ 写回 vault 索引文件
    (链接列 = http://127.0.0.1:23128/open/paper/<附件key>)

CLI serve-links ──→ loopback server ──glob ~/Zotero/storage/<附件key>/*.pdf──→ inline 流原始 PDF
    ──→ cmux 浏览器内联渲染
```

规划(LLM 经 MCP 取数)与执行(CLI 写文件/起服务)分离,只经 **JSON 消息**通信;
CLI 全程不碰 MCP、不读写 `zotero.sqlite`(link-service 只读文件系统)。(INV18)

## 边界(能做 / 不能做)

**能**:
- 本机 Mac 点链接内联看**干净原始** PDF。
- Obsidian 表 managed-block 内增量重建,marker 外人工内容零改动(INV4)。
- URL 只存不透明附件 key,跨机可移植(各机本地 service 自行解析路径)。

**不能(本轮)**:
- PDF 不含批注 —— 批注家在笔记 / Notion 侧,不烧进 PDF。
- 手机 / 远程点 PDF 链接打不开 —— 设计如此(手机读笔记,不读 PDF)。
- 不做 Notion 投影、不做层级索引、不做开机自启(留 T4+)。

## 决策记录 DR-1 — PDF 链接用本机 loopback service 解析附件 key、吐原始 PDF

满足"难逆 + 复杂 + 有取舍"三条,故记录。

- **决策**:投影里的 PDF 链接 = `http://127.0.0.1:<port>/open/paper/<附件key>`;本机 service
  按附件 key glob `~/Zotero/storage`、inline 流式吐原始 PDF。
- **否决项**:
  - `zotero://open-pdf/...` —— 自定义协议,浏览器/Notion 网页端打不开,未装 Zotero 的机器无效。
  - 远程 host / 内网穿透 —— 用户只需本机点 PDF,跨机看 PDF 非需求,徒增复杂度与安全面。
  - 烧入批注的 PDF —— 批注家在笔记 / Notion 侧;要现场导出会耦合 Zotero 导出能力,复杂度高一量级。
- **难逆点**:URL 一旦写进 vault 条目就固化。故 URL 里只存**不透明附件 key**(跨机可移植),
  路径解析留给各机本地 service —— 换机、换目录都不动已写入的链接。
- **已验证**(当前环境实测):绑 `127.0.0.1` + glob storage + inline 流 →
  `200 / Content-Type application/pdf / 16077693 字节 / 开头 %PDF-`。

## 组件契约

### CLI `serve-links`(T1)
- 起 loopback server;`GET /open/paper/<附件key>` → glob `<storage_root>/<附件key>/*.pdf`,
  命中则 200 + `application/pdf` + `Content-Length` + inline 流;无命中 404;路径非法 400。
- **路径逃逸防护**:附件 key 只允许 `[A-Z0-9]+`,glob 前校验,绝不拼入 `..` / 斜杠。
- config 新增 `link_service.port`(默认 23128) 与 `link_service.storage_root`(默认 `~/Zotero/storage`)。

### CLI `project-obsidian`(T2)
- 读 JSON rows(stdin 或 `--rows <file>`),每行含 `title/authors/year/venue/zotero_key/
  attachment_key/arxiv/doi`。
- 调 `obsidian.py` `ensure_managed_block` → `update_managed_block`;链接列由 attachment_key
  拼 `http://127.0.0.1:<port>/open/paper/<attachment_key>`。
- marker 外人工内容零改动(正则只替换 marker 之间);幂等(同 rows 重跑结果一致)。

### 数据来源(宿主 LLM,不在 CLI)
- 经 zotero-mcp `get_item_details` 取字段与附件 key;LLM 组装 JSON rows 交给 CLI。CLI 不碰 MCP。

## Tracer-bullet ticket(依赖序,依次做)

- **T0**(进行中):建 `planning/`、迁 GOALS+HANDOFF、写本规格、GOALS 补 INV17/18 + Phase 2 状态。
- **T1**:link-service 做实(修 guard bug + 附件-key glob + inline 流 + 逃逸防护 + config + `serve-links` + pytest)。
- **T2**:`project-obsidian` 写入(读 JSON → managed-block 精确替换 + pytest)。
- **T3**:端到端 —— 真拿 Text2CAD(item `8USWVHLD`/附件 `S6LZUS6S`)贯穿全线,cmux 点开看 PDF。
- **T4+**(后续轮):N 篇 → 层级索引 → 开机自启(launchd/Windows)→ Notion 投影。

## 收尾(随实现)

sync-projections SKILL.md 对齐 LLM↔CLI 分工;修 references `link-format.md`(端点/bug)、
`obsidian-index-format.md`(`31-papers`→`31-paper`);evals 补 outcomes 用例;CHANGELOG + plugin.json bump。
