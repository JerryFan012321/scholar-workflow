# 正文来源图片：独立测试输入与预期

范围：仅当前hotfix开发树、合成Scalar Reader fixture和pytest隔离目录。正式/实验Vault、
Zotero、外部编辑器、provider、安装缓存和原PDF均不修改，不运行论文分析或实验。

## 输入与操作

1. 既有独立五分支fixture，分别给Method point、Experiments point/claim选择已定义
   `process_diagram`/`experimental_table`。只新增v5布尔开关`markdown_source_images`；
   先运行新增契约用例证明旧生成器不能接受/输出，再实现后重跑。
2. 读取生成Markdown和Canvas完整JSON，检查图片、caption、源页链接所在record，
   原摘录/锚点/五分支及无交叉布局不变。中英标签分别检查。
3. 删除、替换或把自动图移到另一record/文末，再调用正式conformance，必须拒绝。
4. 在claim正文或所选point中已有同图embed时检查不重复；支持直接Markdown、Obsidian
   embed及编码的相对路径。只提文件名、普通链接、转义或code样例不能冒充图片显示。
5. 省略/false开关与旧渲染、序列化相等；v4/legacy和非布尔值拒绝新功能。
6. 用公开paired update规划whole采用、focused保留/拒绝改开关、拒绝whole关闭；
   未选分支、完整Canvas、原内容与人类补充保留。baseline符合已有JSON schema。

## 通过标准与可见产物

- 自动生成与正式conformance都覆盖正文选中图片，缺图或错位置不能validated。
- Canvas完整JSON不因该Markdown选项改变；旧默认输出字节和序列化保持。
- 无新增业务写入、依赖、源图重裁、事实或额外Evidence/图库分区。
- 测试结果单独记入`planning/markdown-source-images-test-results.md`，列出实际命令、
  RED/GREEN、失败原因与未验收边界；不把计划当结果。
- 定向synthetic regression、Ruff、schema/skill校验通过后才称开发验证完成。
  这些不是安装态、人类可读性或科学来源的新认证；旧人工批准不重新索要。
- 提交前一次完整`pytest tests/unit tests/contract`，用已有合成fixture、mock provider与
  pytest隔离目录做跨模块回归，不运行真实外部应用、文库、Field迁移或科研实验。

## 0.41.6 本地打包增量

输入：上述已验证的补图实现与既有模板；只改pyproject、模块版本、两个host manifest及
uv.lock中的本包版本，不改依赖或分析代码。预期四处版本均0.41.6，锁文件与声明一致。

1. 执行既有manifest/runtime版本、69图片契约及10 eval结构用例，预期全部通过；此前
   1896完整回归的代码未变，不把真实业务再次用作开发测试。
2. 本地提交后，以既有make-release.sh的精确runtime路径清单导出归档，展开到新空目录。
   不运行切换/清空worktree的发布步骤，不移动主线或远程release，不手工提交release分支。
3. 检查归档仅含该清单的提交字节；根开发规则、planning/dev-guide/tests/evals、锁文件、
   配置/状态/缓存与个人路径/凭据均不进入。合法相对运行期引用可保留。
4. 在该runtime快照正常build sdist和wheel；只静态检查包METADATA、入口、模块/契约、
   版本与selected-image实现字节，不执行论文输入或调用外部应用。
5. 记录source SHA、归档/构建hash与实际命令结果。安装PATH和cache保持0.41.5。

本地包不等于正式发布、安装或实机验收。获准后仍按既有release脚本/正常安装流程执行，
新开关实机验证仅现有V-JEPA2单对象；源图、内容、Canvas及实验不重新生成。
