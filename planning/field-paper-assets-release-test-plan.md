# 0.43.1 论文附件清单 hotfix：发布、安装与单对象复验

2026-10-10，用户明确“授权”提交、发布和正常安装。使用独立
`codex/hotfix-knowledge-ownership`；不合并main，不切换Hub/worker，不迁移正式资料。

## 输入与先行预期

- 功能代码及独立合成fixture保持上一轮状态：完整2525项unit/contract通过，
  其中39项附件用例；详见field-paper-assets-test-results.md。
- 本轮只同步0.43.1版本和发布回执，依赖及功能范围不增加。补跑版本、双manifest、
  eval schema和附件/论文清单契约，16项skill基础检查及所改Python Ruff。
- runtime-only发行来自干净固定source SHA，经原make-release.sh在独立构建目录生成；
  不含planning/dev-guide/tests/evals、私人路径/密钥、symlink或开发缓存。
- 正常pipx安装固定runtime SHA，Codex正常marketplace更新及plugin add；
  CLI、实际包、双manifest与缓存均0.43.1，安装文件应与发行逐字节一致。
- 上一0.43.0 runtime为3275a80a50dcb031c1bf0a3d785a28df3069f1fc，保留回退点。

## 安装态单对象检查

仅选test既有模范Source 869b0864-f8c9-47e7-94a3-7b283ecc6b60、
Field a6c248d3-23e8-4620-be36-5578b0510de1中的V-JEPA 2。
先读取安装版skill及所需reference，不能用源码环境查询真实Vault。

执行前的声明预期来自既有provider和同Source资产清单，而非待生成stdout：

- 原有资料、分析、Canvas、sidecar四项不变；仍只有一个论文单元。
- 另含六项已声明附件：表2-题注与结果.png、EK100-完整局限.png、
  图2-多阶段训练流程.png、截图复现输入.json、Canvas图片复现输入.json、复现截图.md。
- 六项角色/producer归属保持，不能由目录邻近或同名推断关联。
- 图片/JSON列出但明确不支持原生打开；安全Markdown复现说明可使用已登记阅读器入口。
- 文档入口、未声明笔记、可读标签及诊断不回归。stdout不暴露主机路径/hash。
- 查询只读声明与metadata；不读取论文正文/附件内容，不打开应用、不写业务状态。

步骤：保全选定Source、provider及两份登记文件集合/字节hash基线；执行正常安装CLI的
Markdown/JSON两个公开查询；对照独立声明检查十项文件、URI及状态；保存stdout全等
可见样张及独立机器回执；复核保护范围未变。

产物仅写test上层组合审阅目录：论文清单/领域论文单元清单-0.43.1.md，以及
复现记录/0.43.1-附件清单复验.md和独立.review机器记录；旧0.43.0结果不覆盖。
开发发行/安装结果另记field-paper-assets-release-test-results.md，不把个人路径写入runtime。

## 完成边界

通过仅证明正常安装后的显式附件覆盖、诊断及保护范围；不证明真实点击、美观或全篇
科学支持。PROJECT/实验报告人工评鉴仍独立待确认，原有论文/Canvas/折叠体验不重审。
无实验执行、Zotero写入、正式迁移、服务切换或main合并。
