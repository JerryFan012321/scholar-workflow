# 正文证据截图与复现：0.40.1

本轮输入是单论文的合成图片声明和现有test V-JEPA2两张原生PDF裁剪图。
用户要求正文截图，未要求给Canvas增加图片节点；保留原句、页级入口及已认可布局。

## 独立开发结果

- 原代码新附件测试15失败/1通过，验证复现遗漏真实存在；正常复制测试补强了inventory和归属断言。
- 修复只读资产清单投影、完整inventory和恢复路径，没有新增Hub服务或ROI工具。
- 17附件测试涵盖完整导出/恢复、未知owner、重名、占用路径、路径逃逸、symlink、缺图、hash/size、
  清单重复键/未知字段、并发变化及无清单的absence变化。
- 与28个v5测试组合45通过；图片body+原正文canvas_summary的整个Canvas JSON投影守恒。
- 既有knowledge导出/恢复组合72通过（新增absence测试之前）；Ruff/diff通过。
- 完整unit/contract：1713 passed、11既有warnings，86.56秒；Skill validator通过。
- 真实分析尚未改写，安装仍0.40.0；下一步正常hotfix安装后进行单篇更新。

## 安装态范围与人工评鉴

正常hotfix发布安装后，仅通过公开stage-update/commit-bundle更新test单篇；采用fresh live provider CAS，
不使用portable包中的投影revision作为live基线。两张PNG和无秘密裁剪输入置于单篇attachments，
明确assets归属；复现包须包含它们及清单。随后只读check-bundle和新目录归属恢复验证字节/归属。

人工对象是该篇正文中的表2完整表和EK100局限段落：应当读清标题/列名/数值及完整段落，
原文入口仍在Obsidian ZotFlow按物理页打开。用户未确认前标为待人工评鉴。
不批量分析/迁移、不重跑已验证实验、不改模范项目清单、不合并main、不切换服务。
