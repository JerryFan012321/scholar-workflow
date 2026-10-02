# 0.31.0：test Vault 单篇只读实验

日期：2026-10-02。用户批准只使用已验收的 V-JEPA 2 样本，不改写或重新生成内容。

## 对象与操作

- Vault：Obsidian registry 中的 `test`。
- 目录：`Scholar Workflow 实验/V-JEPA 2/v4-审议候选/`；不选择旧 DRAFT 或其他归因候选。
- 使用正常 pipx site-packages 的已安装 `0.31.0`，读取 IR、Markdown、Canvas、sidecar。
- 调用已安装包的成对 conformance 校验；检查节点/边、来源 URI 和文件字节。
- Obsidian CLI 在 test Vault 分别打开现有分析 Markdown 与 Canvas，新标签。
- 未运行生成脚本、写笔记、移动文件、登记项目/Field、启动 Hub 或修改正式文库。

## 实际结果

| 项目 | 实际结果 | 状态 |
|---|---|---|
| 安装版本 | 0.31.0，实际 pipx package | pass |
| 成对格式校验 | `ok=true`，0 findings | pass |
| 完整框架 | IR v4，Abstract / Introduction / Method / Limitation | pass |
| 内容与可编辑数据 | 22 claims、46 points，58 个 text 节点、57 条边 | pass（结构） |
| 无箭头连接 | 0 条带箭头边；完整格式校验通过；用户认可外观 | pass |
| 机器注释 | Markdown/Canvas 未含 `sw-analysis-claim` | pass |
| 阅读器入口 | 25 个不同页级 URI，全部指向 test 的 ZotFlow Library Reader / `QR4ZU2S9`；用户确认本轮抽查点击效果 | pass（不冒充逐页科学来源审查） |
| 配套归属 | IR、Markdown、Canvas、sidecar 同目录、普通文件，非 symlink | pass（文件共置，不冒充正式 owner 登记） |
| Obsidian 打开 | 两次 CLI 均返回 Opened；Advanced Canvas / ZotFlow 已启用 | pass（入口，未冒充 GUI 目视验收） |
| 输入保护 | 格式校验与打开前后，四文件 SHA-256 均一致 | pass |
| 人工布局/编辑/原文跳页/正文反链 | 2026-10-02 用户明确回复“人工评鉴ok” | pass（仅本样张及上述操作） |

来源页列表：2、4、5、6、7、8、9、10、11、12、13、14、15、16、17、18、19、20、21、
23、37、40、41、44、45。这里只证明现有 URI 参数一致，不证明 PDF 正文支持每项论述；
没有重新核验论文事实、批注同步或逐页点击；本轮抽查交互由用户确认。

## 人工评鉴操作

在已打开的 Obsidian test Vault Canvas 标签中：

1. 查看整体布局、字体、留白是否仍满意。
2. 双击一个文本框，确认可进入编辑模式，然后按 Esc；不要输入或拖动节点。
3. 抽查一条“原文”链接：在 Obsidian 内 ZotFlow 打开正确附件并到对应页。
4. 点击同一节点的“正文”反链：回到对应分析 Markdown 的论点/论据。

用户已确认本轮 GUI 评鉴通过。此实验证明既有分析产物在新版安装下可校验/打开且抽查交互获认可，
不验证新的项目资料总览，也不意味着完整职责解耦、正式 Vault 迁移或 main 合并已完成。
随后提出的正文逐字摘录属于新的格式变更，不纳入本次已通过的旧样张验收。
