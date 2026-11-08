# explore-knowledge

以可编辑维度、条件和结果组织研究工作，查看带依据的关系与完整资料入口。
这一层引用已有完整知识资产单元，不改分析正文、Canvas、sidecar、原文或图片。

本轮交互设计仍待讨论。旧网页不再作为推荐工作流；触发本 Skill 不会自动打开它、
另建一个界面或迁移数据。目前也没有已经交付的原生替代界面。

## 现有文件与命令操作

选定已有目录和需要的操作。只读查询和 Markdown 输出可以使用：

```sh
scholar-workflow knowledge exploration-query --root /path/to/selected/folder --selection query.yml
scholar-workflow knowledge exploration-export --root /path/to/selected/folder
```

不传 `--selection` 时使用默认筛选。没有 manifest 时只返回内存中的空模型，不会自动建文件。
导出只向终端输出；保存独立导航文档是另一个明确的文件操作，放在所选目录、论文包之外，
保持相对链接含义，不自动插入已有论文正文。

现有数据仍保存在 `.scholar-workflow/exploration.yml`，包括可扩展维度、完整论文引用、
条件化记录、带证据的关系与保存视图。初始四个维度不是封闭分类。
筛选先匹配同一条研究记录，再汇总工作，避免把不同实验的基座、任务和结果拼在一起。
条件与结果一起展示，作者报告、本地复现、独立评测和分析判断分别标注。

明确修改时，`exploration-init` 创建新 manifest，`exploration-apply` 按当前版本保存。
`exploration-import` 先预览已有 Source/Field 的论文、Blog和技术文档完整单元，再按版本应用。
引用带入全部声明资产，不复制或重新分析正文；普通模型保存不能添加单元身份或改变资产归属。
可以直接编辑文件，但仍遵守同一 schema 和归属规则；外部修改后重读，冲突不能覆盖较新版本。
旧的未登记非论文记录保留可读，并显示归属未核实；受管编辑不修改它及相关关系记录，
也不因补填一个ID就冒充完成登记。其他尚无正式登记入口的类型如实报告缺口。

可读结果保留研究定位、条件与结果、关系，以及全部声明的本地／在线／原生入口和缺失诊断。
原论文包仍由已有工具阅读和编辑 Markdown、Canvas；查询或导出不会启动这些工具，
也不能证明链接已经在阅读器中实际打开。

目录接入、测试／正式隔离与分层检查仍遵守
[Vault 接入与隔离](../../references/vault-connections.md)，不成为每次查询的自动前置操作。

## 保留的旧网页技术入口

只有明确要求使用既有界面时才运行：

```sh
scholar-workflow knowledge explore --root /path/to/selected/folder
```

它使用本机动态端口，可能打开浏览器或 cmux surface；终端保持运行，Ctrl-C 停止。
`--no-open` 只显示本次会话地址。它不是上述文件操作的必要条件，也不代表未来交互设计方向。

精确命令、文件格式和现有边界见[运行契约](../../references/knowledge-exploration.md)。
本批开发完成不代表已正常安装、原生链接已逐项打开或人工使用体验通过。
