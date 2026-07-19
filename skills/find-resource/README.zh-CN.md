# find-resource

查找与定位学术资源,两种模式:

- **发现** —— 规范化标识符(DOI / arXiv ID / 标题),检查本地库和 Zotero 是否已有,
  并在获得明确授权时查询 Crossref / OpenAlex / Semantic Scholar。返回候选列表,
  含匹配依据和 arXiv PDF 可用性。
- **定位** —— 把已有论文或文档解析为本地路径和本地链接服务 URL,不复制文件。

全程只读。不从非 arXiv 来源下载 PDF,不写任何文件。

完整流程与约束见 [SKILL.md](./SKILL.md)。
