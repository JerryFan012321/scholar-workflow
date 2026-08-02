# ingest-resource

经 zotero-mcp 把论文导入、把技术文档归档到本地库。一篇论文只需两样:PDF(来自 arXiv)
和元数据(来自权威网源,绝不从 PDF 解析)。分三个阶段:

- **存在性核验(只读)** —— 规范化标识符(DOI / title+authors;arXiv id 只是下载源标识、
  非身份),经 zotero-mcp 两步核验:`search_library` 召回 → `get_item_details` 回读确认,
  结果为 exact / conflict / none。`write_item` 是纯 create、不判重,故每次 create 前必须
  先做此核验。
- **获取元数据(只读联网)** —— 对新条目,从 arXiv abs / CVF / DBLP / 出版社读取元数据;
  有正式发表版本时,会议名覆盖 arXiv 预印本名头;查不到的次要字段留空,不编造。
- **写入(经 zotero-mcp)** —— 先问论文归入哪个分类,把 arXiv PDF 下载到 `paper_inbox`,
  再 `write_item` create + import 挂载,并 `add_items_to_collection` 归类。新增性写入在
  用户已下达指令时直接执行,仅删除/覆盖/合并须批准。技术文档复制进 Vault 并写来源/散列元数据。

下载的论文 PDF 只进 `paper_inbox`,技术文档只进 Vault。所有 Zotero 访问都经 zotero-mcp,
插件绝不直接写 `zotero.sqlite`。

## 跨机同步(配置须知)

论文 PDF 保持 **imported(存进 Zotero,`linkMode 0`)**。这样 Zotero 文件同步(Zotero
Storage 或 WebDAV,如坚果云的 WebDAV 端点)会自动把它们带到每台机器——你库里其余附件本来
就靠这套机制。

**不要**用 **ZotMoov** 这类会把附件转成*链接文件(linked file)*并移到外部目录的插件。
Zotero 文件同步**不同步链接文件**,这些 PDF 本体永远到不了另一台机器;更糟的是,若插件的
目标目录不在 Zotero 的「链接附件基目录」内,链接会存成绝对路径(`/Users/…`),文件被锁死在
单机。如果你确实想要一个可在文件管理器里浏览的外部目录结构,就必须自己同步那个目录(坚果云
桌面客户端 / Dropbox),并在每台机器把基目录指向它——这是另一套、更易出错的方案。省心的做法是:
附件保持 imported,交给 Zotero 同步。

完整流程与约束见 [SKILL.md](./SKILL.md)。
