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
- 开发阶段真实分析尚未改写、安装仍0.40.0；下方记录此后实际安装与单篇更新，不篡改开发结果。

## 正常发布、安装与单对象实证

source `b644f82001395bcb43a1e2145cada80d57eb1b09`，runtime
`21c29a734795071e0cdfb0a57575ccde31984756`。正常release脚本在独立干净clone构建，
pipx固定已推送runtime commit安装，Codex marketplace正常更新；PATH CLI、direct_url与两个
已安装plugin manifest核实为0.40.1，没有源码直跑或手改缓存。main未合并，服务未切换。
本地旧release基线曾导致非fast-forward拒绝；旧分支保留后从权威remote release重新构建并正常推送，
未force/reset。未发布SHA的第一次安装失败没有替换旧产品；成功后才执行真实业务更新。

仅原test V-JEPA2的两处方法摘录和两处正文图片body更新，公开stage-update/commit-bundle及
KnowledgeChangeSet登记成功，commit ID为`vjepa2-0401-evidence-images-20261005-01`。
最终三文件hash为Markdown `47166d28…`、Canvas `826b92db…`、sidecar `eb6072dd…`；公开
check-bundle conformant/零findings，36claims、69内容、106节点、105边。
全部节点几何/样式、所有连线、其余claims保留；Canvas仅方法模块2节点增加物理第5页原文入口。
两PNG、裁剪输入与复现说明放在单篇attachments，显式assets.yml持有归属，不给Canvas增加图片。
Zotero原PDF、Field manifest、既有Canvas manifest和实际host registry的保护hash未变。

## 已执行的带图复现

installed公开reproduction-plan明确列出13文件/4附件；复制到唯一新test“复现Source”，隔离
SCHOLAR_WORKFLOW_HOME并经公开registration-plan/register、restore-plan/restore恢复缺失归属。
恢复不重写正文，不导入旧主机回执，不打包Zotero PDF或密钥；源身份经Local API核实。
恢复后再导出package digest与原包完全相同：
`sha256:35505054dc8987eac6c9ec13d4a1749a2606fbdfcb5f6ee4058e36f9ba39e6c6`。
两PNG源/副本hash均实际一致，两份三文件conformance通过。该结果是本机隔离host-state重放，
不是物理另一台主机GUI、verified backup、科学全项或人工阅读通过。
完整公开输入与实际回执见test“正文证据截图-0.40.1/实际验收结果.json”；中文入口为同目录
“本轮可见成果.md”，不把机器回执当阅读正文。

Obsidian原生打开请求及当前文件身份确认，后台两PNG为1200×440/1200×285。本轮进一步在阅读
视图定位两处正文，并逐张目视确认新capture实际显示完整表格/完整段落及相邻原文摘录和链接。
真实预览保存在同一test目录“表2正文-实际预览.png”“EK100正文-实际预览.png”；早期停留顶部或
延迟一帧的截图不作为该区域证据。它证明本机实际呈现，不代替用户对字号、位置与便利性的评鉴，
也不证明PDF页链接本轮已点击。人工仍需检查第14页完整表/第18页完整段落的呈现。
本轮仅开发记录留档，10项eval结构测试通过（0.02秒），diff空白检查通过；未改运行代码。
回退为0.40.0 runtime `aa1861df517e0e22bab2bc01780e327366475aa7`；旧三文件保留在成对提交
journal中，后续人工编辑后不得无条件恢复覆盖。

## 安装态范围与人工评鉴

已通过正常hotfix安装后公开stage-update/commit-bundle更新test单篇；采用fresh live provider CAS，
不使用portable包中的投影revision作为live基线。两张PNG和无秘密裁剪输入置于单篇attachments，
明确assets归属；复现包已包含它们及清单。只读check-bundle和新目录归属恢复已验证字节/归属。

人工对象是该篇正文中的表2完整表和EK100局限段落：应当读清标题/列名/数值及完整段落，
原文入口仍在Obsidian ZotFlow按物理页打开。用户未确认前标为待人工评鉴。
不批量分析/迁移、不重跑已验证实验、不改模范项目清单、不合并main、不切换服务。
