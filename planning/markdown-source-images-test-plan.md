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
