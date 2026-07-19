# Zotero 字段映射

## 论文条目（journalArticle / conferencePaper / preprint）

| Zotero 字段 | 来源 | 说明 |
|---|---|---|
| `title` | 元数据 | 必填 |
| `creators` | 元数据 | author 列表 |
| `DOI` | 标识符 | 有则填写 |
| `url` | arXiv / DOI URL | 优先 arXiv |
| `date` | 年份 | YYYY 格式 |
| `publicationTitle` | venue | 期刊名 |
| `conferenceName` | venue | 会议名 |
| `abstractNote` | 元数据 | 摘要 |
| `extra` | arXiv ID | `arXiv: 2401.01234` 格式 |
| `tags` | 用户 + 系统 | 主题标签 |
| `collections` | 用户确认 | Collection key 列表 |

## 附件（linked_file）

| 字段 | 值 |
|---|---|
| `linkMode` | `linked_file` |
| `path` | PDF 规范化绝对路径（由 ZotMoov 或 Bridge 最终确定） |
| `contentType` | `application/pdf` |
| `title` | `{arxiv_id}.pdf` 或 `{first_author}_{year}_{short_title}.pdf` |

## 幂等判重依据

优先级：DOI > arXiv 基础 ID > 规范化标题 + 第一作者 + 年份

同一 arXiv 论文的不同版本（v1/v2/v3）不得创建多个 Zotero 条目。
