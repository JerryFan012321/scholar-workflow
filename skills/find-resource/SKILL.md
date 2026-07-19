---
name: find-resource
description: Search for papers, verify paper identity, build candidate lists, locate existing papers or documents in the local library, open resources in cmux. Triggers: 'find papers', 'search literature', 'where is this paper', 'locate document', '找论文', '搜索论文', '这篇论文在哪', '定位文档'.
---

# find-resource

## 触发
- 用户搜索论文、核验论文身份、整理候选列表
- 用户询问某篇论文/文档在哪里、要求定位或在 cmux 中打开

## 步骤

1. 判断请求类型：**发现**（搜索新资源）还是**定位**（找已有资源）
2. **发现模式**
   - 规范化输入标识符（DOI / arXiv ID / 标题）
   - 检查本地状态库和 Zotero 是否已有该资源
   - 用户明确要求时联网查询（Crossref / OpenAlex / Semantic Scholar）
   - 返回候选列表、匹配依据、arXiv PDF 可用性、已有状态
3. **定位模式**
   - 论文：先查 Zotero item/attachment key，再解析 `papers_root` 下相对路径
   - 技术文档：从状态映射解析 Vault 相对路径
   - 返回本地路径和本地链接服务 URL，默认不复制文件

## 输出
候选列表（发现）或本地路径 + URL（定位）

## 约束
- 联网搜索需用户明确授权
- 可使用 Crossref / OpenAlex 等核验元数据，但不得从这些来源下载 PDF
- 发现阶段不产生任何文件写入
- 不得从非 arXiv 来源传递论文 PDF
