# 原生工具交互：单篇 cmux 阅读验收

## 当前结果

2026-10-05，已安装 Scholar Workflow 0.40.1 与 cmux 0.64.25（106）在一个独立工作区实际显示
V-JEPA 2 的本机原 PDF，原生文件预览标签显示 48 页。新鲜 CUA 窗口截图可见 PDF 正文、
页缩略图和缩放控件；命令接受与实际显示分别核实。不需要 Hub、Scholar workspace 注册或绑定。

单对象中文说明、独立验证方案和分离的实际结果 JSON 位于 test Vault 的
“Scholar Workflow 实验/原生工具验收-0.40.1”。机器记录保留本次引用与保护哈希；
这些实例内引用和本机 locator 不成为便携知识身份或运行期硬编码。

## 实际操作与失败边界

1. 安装版 `scholar-workflow zotero get T3RY3HUA --children` 核实原条目与 PDF 子附件 QR4ZU2S9；
   PDF 的本机位置来自当次 Local API enclosure，不根据 storage 目录猜测。
2. 已安装 cmux 原先未运行，正常启动原应用，不升级、不改变设置。
3. 外部 CLI 被本机仅允许 cmux 子进程的控制模式拒绝。这是实际失败结果，未降低安全模式。
4. 通过原生界面创建一个独立空工作区，在它自己的终端运行公开 `identify --json`，然后
   `open <本次附件位置> --workspace <返回引用> --pane <返回引用> --focus true`。
   仅命名和使用这个新工作区，没有向已有用户终端输入命令。
5. 原生 PDF 确实显示于“Scholar 原生阅读验收”。再次窗口截图显示同一预览；原 PDF、
   当前分析正文、Canvas 和 sidecar 四个 SHA256 全部与操作前一致。

cmux 安装版 `open --help` 还明确默认目的地为调用者的当前 workspace/surface。
人可在目标工作区自己的终端直接 `open`，不必理解 Scholar instance、lease 或 nonce。
外部 agent 不伪造 cmux 调用环境或读取控制凭据；需要时仅使用已授权的原生界面。

## 完成与未完成的区分

| 项目 | 状态 | 证据与边界 |
|---|---|---|
| 实际本机 PDF 显示 | 已验证 | 当前原生窗口可见，48 页；不是只看 help 或模拟回执 |
| 对象身份及定位 | 已验证 | Local API 父子关系、类型、enclosure、PDF hash；只核此论文 |
| 原件保护 | 已验证 | PDF/Markdown/Canvas/sidecar 四哈希保持 |
| 可照做的操作与失败诊断 | 已保存 | test Vault 中文说明与实际结果分离 |
| 翻页、缩放及打开位置是否顺手 | 待人工评鉴 | 用户打开上述工作区，按说明操作并判断 |
| Zotero 数据库批注显示或写回 | 未提供 | 此入口是原 PDF 预览，不是内嵌 Zotero reader 或实时同步 |
| 第一阶段全部完成 | 未证明 | 项目清单生效、新截图体验及全项来源支持仍独立待处理 |

本轮不修改运行期代码、skill 或已安装产品，因此不生成另一个 hotfix，不重跑已有效实验，
不重新排版 Canvas、不迁移正式 Vault、不操作 Zotero 内容，也不合并 main。
本结果覆盖先前“cmux 尚无 live socket / 原生窗口未通过”的当时状态，不篡改历史记录。

文档留档检查：10项eval schema结构测试通过（0.02秒），实际结果JSON可解析且明确保留
人工pending/阶段未完成，git diff --check通过。该范围只守护记录结构，不冒称GUI或科学验收。
