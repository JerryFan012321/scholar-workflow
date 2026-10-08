# 正文摘录折叠：开发验证结果

日期：2026-10-08。工作分支：`codex/hotfix-canvas-images-release`。
源码增量基于已提交的0.41.7；实现阶段没有发布或安装。用户实际安装仍保留0.41.7。

后续本地准备：只将已验证的同一能力包元数据统一至0.41.8，补版本/格式/eval回归后
准备源码提交及runtime-only候选；正式发布安装、真实单篇效果和人工评鉴仍另行授权。
以下保留实现阶段结果；本地构建结果以实际审计记录为准。
0.41.8版本准备回归已实际完成：64通过（1.13秒），lock检查24包一致，diff通过；
依赖pin和已验证功能代码不变，2035完整功能回归仍是本轮实现的证据。
远程release只读核验为aeed349e8b71ae19b33635c94ac9df29f901662e，即已安装0.41.7；
共享工作树的本地release/origin-release仍旧，不据其旧ref冒称当前服务器或安装版本。

## 本轮改了什么

- 新增显式`profile.markdown_folded_quotes: true`，要求已开启摘录的v4/v5接口。
- 所有已提供的摘录使用原生默认折叠quote callout。标题保留同点原文链接；展开后
  完整句子、必要语境和精确粗体保持。论点、锚点和图片留在折叠块外。
- 新分析的输出规范明确逐条呈现已核实的直接支持或推断依据，不只处理三个例子。
  无法确定支持关系则保留来源/语义缺口，不能机械全段加粗。
- 旧省略/false输入保留原投影与序列化；既有文档对显式整篇成对采用，局部更新不能
  更改格式，采用后不能普通更新关闭；人工内容冲突仍停止。
- 完整Canvas内容、几何、原文入口、正文反链及图片契约不变。

## 独立输入与实际测试结果

计划：`folded-quotes-test-plan.md`。输入为既有合成IR4/IR5、合成SOURCE三整句及
预先手写的`tests/fixtures/analysis-folded-quotes/EXPECTED.md`；不以生成结果反推预期。

| 检查 | 实际结果 |
|---|---|
| 实现前手写预期正例 | 1失败/23未选：旧接口不接受folded参数，预期RED |
| 第一轮实现 | 10失败/14通过：conformance的四个调用点漏传新选项；补齐后原24项通过 |
| 扩充独立边界用例 | 首轮46通过/2失败：测试选错v5含method的claim，未进入产品执行；修正测试对象后48项通过 |
| 加入图片在折叠块外的组合用例 | 49通过，1.12秒 |
| 既有摘录、强调、图片、stage-update及eval结构定向回归 | 286通过，6.29秒 |
| 完整unit/contract回归 | 2035通过，11条既有依赖/fork弃用警告，94.50秒；没有失败 |
| Ruff与skill入口校验 | 通过；首次Ruff import顺序诊断已修正 |

49项覆盖中文/英文、作者陈述/推断、claim/point、PDF/登记Markdown、ZotFlow链接、
多来源、源文本含Markdown/HTML/callout/空行的字面展示、callout/链接/位置篡改拒绝、
whole采用/focused保留、旧字节兼容及人工编辑冲突。成对测试直接比较完整Canvas JSON，
不是只检查节点数。图片组合证明embed/题注仍在quote callout之外。

完整回归命令为`rtk proxy uv run --offline --with pytest python -m pytest tests/unit tests/contract -q --tb=short`。
Ruff检查全部改动Python文件通过，skill-creator的入口校验通过，`git diff --check`通过。

运行命令均经`rtk proxy uv run --offline --with pytest python -m pytest`；
测试是开发合成检查，不冒充已安装产品。没有真实Vault/Zotero/Provider/项目写入，
没有PDF下载或裁图、业务重分析、服务/worker变动、安装缓存修改或main合并。

## 评测与尚未完成的边界

description及触发策略不变，既有单篇/批量/代码只读和非论文仓库排除路由保持；
来源/引用安全case保留逐字、限定、推断与事实的区别，明确完整覆盖不能编造支持。
新增folded outcome保持pending；原强调outcome纠正为0.41.7已安装、单篇仅三处采用，
仍不是全部69记录/98段摘录已核实并完成呈现。自动测试不认证科学支持。

下一次安装态只需正常hotfix部署后，用同一V-JEPA2受控样本审阅：打开新正文，
看到引用标题和原文链接；点击展开/收起，确认完整句子与直接证据粗体清楚；
点击原文链接仍到同一ZotFlow页；图片保持可见，既有Canvas不变。需在会话中再次
明确对象和方法，用户确认前记“待人工评鉴”，不重开仍有效的Canvas/图片审批。
本轮不创建该候选，不修改现有样本，也不把开发测试当成该人工结果。

“文章正文的图片要尽量采用……”尚未补全；未替用户猜测或新增图片行为。
