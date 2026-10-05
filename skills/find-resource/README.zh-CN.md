# find-resource

查找与定位学术资源：

- **发现** —— 规范化标识符(DOI / arXiv ID / 标题),检查 Zotero 是否已有,
  并只读查询 Crossref / OpenAlex / Semantic Scholar 元数据。返回候选列表,
  含匹配依据和 arXiv PDF 可用性。
- **定位** —— 返回已有论文的条目/附件身份和稳定阅读 URI，或已登记文档的 Vault
  相对路径；不复制文件。
- **按请求打开** —— 使用原生阅读器或cmux当前/明确选择的位置，无需Hub或workspace绑定。
  [打开说明](./references/resource-location.md#requested-native-opening)包含实时本机PDF定位、
  最短命令和控制失败的处理。命令被接受不等于实际显示；原PDF不包含Zotero数据库批注。

全程只读。不从非 arXiv 来源下载 PDF,不写任何文件。

完整流程与约束见 [SKILL.md](./SKILL.md)。
