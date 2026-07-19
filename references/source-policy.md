# 来源策略

## 论文 PDF

- **唯一自动获取来源：arXiv**
- 其他来源（Crossref、OpenAlex、Semantic Scholar、出版社页面）只能用于元数据核验和论文身份解析
- 禁止从出版社、搜索引擎、网盘或其他非 arXiv 站点自动下载论文全文
- 禁止绕过付费墙、验证码、登录或访问控制

## arXiv 版本处理

- `2401.01234`、`2401.01234v1`、`2401.01234v2` 视为同一论文
- 下载时获取最新版本；arXiv ID 存储规范化基础 ID（不含版本号）
- Zotero 条目只创建一个，不因版本升级创建第二个条目

## 元数据来源优先级

1. DOI（最高可信度）
2. arXiv API
3. Crossref / OpenAlex
4. Semantic Scholar
5. 用户手动提供（需标注来源）

## 无 arXiv PDF 处理

arXiv 上不存在 PDF 时：记录元数据和候选状态，标记 `no_arxiv_pdf`，不自动从其他来源获取，由用户决定后续操作。
