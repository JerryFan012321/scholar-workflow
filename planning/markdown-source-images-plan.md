# 正文图片：单对象增量

用户要求分析正文也显示图片。对象仅为test已登记模范Source的V-JEPA 2；已有表2与局限段落
截图保留，仅补已通过的图2。直接使用已安装0.41.5支持的IR point.text图片与plain
canvas_summary，不引入新配置、重分析、裁剪或生成器变化。

输入是当前baseline文档、当前provider修订与三文件物理hash；图片引用现有明确归属资产。
将图2放入Method Overview的steps点，原步骤作为Canvas summary保持；原句摘录、来源和
准确块锚点均不改。两图原人工评鉴继续有效，正文新增图片的实际阅读呈现另行展示。

执行前准备独立输入与比较：public stage必须validated/零findings；新Markdown移除唯一新增
图2说明/图片字符串后与旧文逐字相同；新Canvas完整JSON（节点、边、样式、布局、metadata）
与旧图相等；IR除该点文字及等价summary外相等，69内容/108节点/107边及71反链保持。
否则停止，不提交、不放宽校验。通过后正常public paired commit/provider apply，核对所有
回执hash与12非trio文件；公开check和导出15文件通过；在Obsidian读取模式显示图2与表2。

开发文件只修改现有输出规范及验收状态，不发布新runtime或改安装缓存。独立新根复现包
保留原验收时的内容，不建立隐藏同步。可见产物为原test样张正文、截图及分离的实际结果。

最后追加两项独立英文/中文合成回归，复用仓库虚构scalar-reader fixture的method点；
仅增加正文相对图片及等价Canvas summary，预期Markdown移除唯一增量后精确等于原文、
Canvas完整相同且conformance通过。同时运行eval schema及skill元数据校验；不访问真实文库。
真实正文显示被用户切换界面打断，不用其他文件截图作为通过证据；新增阅读体验待人确认。

原生打开后若编辑器仅再次重编码已打开Canvas，最终导出会安全拒绝旧物理hash。
只在完整JSON与已提交暂存图相等、其他14文件不变时，使用当前三hash/修订及登记旧hash
做一次公开metadata acknowledgement并再导出；不重新stage/commit/分析。无法精确证明则停止。

实际结果：installed0.41.5单次stage零修复validated、独立比较通过，paired commit/provider
apply及最终check/15文件导出通过。正文3图（只新增图2），Canvas完整JSON保持。
开发态v5与eval schema组合40 passed（0.82秒），含新增两语合成守恒用例；skill quick_validate、
Ruff与diff检查通过。没有运行完整1857回归或重复真实业务；现有运行时版本不变。
