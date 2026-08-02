# recommend-papers(论文推荐)

每日论文推荐 feed。聚合四个互补的推荐源,按 arXiv id 合并去重,再对你挑出的 shortlist
经 NotebookLM 略读,产出一份便宜的**推荐清单(Reading Report)**——它只是决策辅助,不落
vault。看中的论文走常规的 `find-resource` / `ingest-resource` 管线入库。

## 四个推荐源

| 源 | 信号面 | 登录 |
|---|---|---|
| Semantic Scholar Recommendations | 用你的 Zotero 库当 positive 种子 | 无 |
| Scholar Inbox | 训练型个性化 digest(长期 up/down vote 训出偏好) | session cookie(约 7 天) |
| S2 author watchlist | 你登记的研究者/实验室的新作 | 无 |
| HuggingFace Daily Papers | 社区 upvote 热度 | 无 |

每个源吐一个规范化候选(`arxiv_id`、标题、作者、来源、分数、摘要片段、url)。按 arXiv id
去重,并记录每个贡献来源,便于看出重叠。

## 漏斗怎么走

1. **全量可选项**——聚合器只打印**元数据级**候选(便宜,不 skim)。
2. **细化**——按兴趣 / 项目关键词过滤,或手动挑,得到 shortlist。
3. **略读**——只有 shortlist 进 NotebookLM(约 500 token/问,而读一篇 PDF 约 50K token)。
4. **推荐清单**——一份供你拍板的简短 markdown。临时性;看中的再入库。

## 配置

1. 复制配置模板:
   ```bash
   cp references/recommend.example.yml ~/.config/scholar-workflow/recommend.yml
   ```
   编辑 `interests`、`sources` 开关、`daily_limit`、`watchlist`。
   可选项目层:`~/.config/scholar-workflow/projects/<当前目录名>.yml`
   (interests/watchlist 为追加;其余键覆盖)。

2. 安装 NotebookLM 自动化(略读级):
   ```bash
   pipx install "notebooklm-py[browser]"
   notebooklm login
   ```
   会存真实 Google 登录态——建议用小号。

3. Scholar Inbox(可选第四源)需要 session cookie。vendor 的客户端经 `playwright-cli`
   驱动浏览器登录;cookie 存到 `~/.config/scholar-workflow/scholar-inbox/session.json`
   (chmod 600),约 7 天有效。没有它则跳过该源,用其余三源。

## Watchlist(关注作者)

给出研究者姓名(加机构或代表作),skill 解析出稳定的 Semantic Scholar `authorId` 存进
`watchlist`,规避重名问题(如众多作者都叫 "He Wang")。台账是个人数据——gitignored、只留模板。

## 排障

- **某源出现在 `skipped`**——该源失败或未配置(无种子、watchlist 为空、Scholar Inbox
  无 session)。其余源照常完成。
- **HF Daily 超时**——它走系统 HTTP 代理(`httpx` `trust_env`,即 `HTTP_PROXY`/`HTTPS_PROXY`
  环境变量),S2 走直连。这些路径在适配器里固定;HF Daily 连不上时先查代理环境变量。
- **NotebookLM 不可达**——回落到纯元数据推荐,或经 `analyze-paper` / `get_content` 阅读
  (更慢、更费 token)。

## 引用声明

`scripts/scholar_inbox/` 下的 Scholar Inbox 客户端改编自
[sjh-skills](https://github.com/jiahao-shao1/sjh-skills)(MIT License,Copyright (c)
2026 Jiahao Shao)。详见 `scripts/THIRD_PARTY_LICENSES`。
