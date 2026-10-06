# Canvas 图片范围与配对正文反链：开发核验结果

2026-10-06。开发分支 `codex/hotfix-canvas-images-release`；0.41.3已正常发布安装并完成单篇候选原生反链核验。

## 当前安装与单对象可见结果

- source `ae3c5a1088db3c40eca8a65ca1d1277866a418ba`；runtime-only release
  `2e8228fceb7f8f9b34fb28373778ea02b56f043d`，通过正常非force Git发布。
- pipx固定runtime commit安装CLI0.41.3，实际site-packages模型与源码逐字匹配；
  Codex marketplace正常upgrade/add安装0.41.3，缓存输出模板与源码逐字匹配，双manifest同步。
  回退点为0.41.2 runtime `739e1204c35e2442d32123060cca0f57c06f7c63`，不假定旧缓存仍在。
- 仅test Vault新建`Scholar Workflow 实验/Canvas图片验收-0.41.3`。复用旧候选完整IR与图片，
  不重分析。首次平铺路径请求被exit2拒绝；仅将三个原输入复制成接口要求的论文目录结构，
  不改校验、不登记Source。第二请求的安装态public stage为validated/零问题/canonical_written=false。
- 独立核对：Markdown逐字相同，69内容、108节点、107边；节点ID/几何/样式/顺序及所有边保持，
  71条正文反链改为新目录确切正文路径；source、quote、claims/points和四个附件逐字保持。
  Canvas仅图2/表2，EK100段落图片只在Markdown。安装态check-bundle为conformant、零问题。
- Obsidian原生显示图2与表2，真实点击两张图卡的正文反链准确到新文件的steps/finding-1块，
  原生截图与打开位置均留档；已读取检查保存的两张显示截图，不以静态resolver代替鼠标操作。
- 编辑器查看使Canvas物理hash从f9baea9b…变为462c6eec…；完整节点/边独立比较仍相同，
  再次public check零问题。三文件sidecar不手改，非canonical审阅不做provider hash acknowledgement。
- canonical三hash及原PDF匹配此前保护值，项目总览314a357b…保持；主checkout无关人工审阅文件不动。

本轮没有重新点击PDF页入口、重新验证科学支持或重跑实验。图片人工裁剪/可读性/美观仍pending，
完整带图canonical归属复现及项目覆盖授权仍待完成，G17继续active。以下保留开发时的历史状态。

## 用户格式规则

Canvas只加入实验数据表和关键流程图；段落裁剪和逐字摘录仍在Markdown。图片不替代完整
五分支、具名可编辑节点、逐点来源入口和正文反链，对齐、直角无箭头连线与无交叉继续生效。
规则已经在输出模板、v5 typed image模型与JSON Schema中维护；本轮没有扩大图片种类。

## 单对象失败与修复

此前当前0.41.2单篇候选实际显示图2/表2，但正文反链打开旧同名笔记。独立A/B原生鼠标
点击确认短名及./短名失败，明确Vault相对路径命中B的确切块。不把静态解析通过当作点击
通过，也不声称已经确定第三方组件根因。

开发实现仅增加v5可选canvas_note_path显示路由：全部claim、point、图卡都指向该配对正文。
文件名必须匹配，unsafe/absolute/URL/片段/控制字符拒绝；旧默认与序列化不变。明确whole
采用/重绑定，focused保留。正式提交由可信Source和非秘密Obsidian registry计算真实目标，
错误目标或无法解析在写入之前拒绝。复现时同Vault内移动Source也报告重绑定，不自动改内容。

## 独立自动测试

- 首先运行2项新增正向用例，因旧模型/Schema不接受新字段而预期失败，之后才实现。
- 完成图卡、路径、whole/focused、实际commit写入前拒绝、复制位置诊断边界；最新受影响
  analysis/update/commit/image/reproduction/eval组合246通过（6.31秒）。其中eval Schema10项。
- 受影响代码与新测试Ruff通过，git diff格式检查通过。Markdown、节点ID/几何/样式与边
  均有独立守恒断言；合成图卡实际参与新目标检查，不只用无图片fixture冒称覆盖图片。
- 完整unit/contract：1827通过、2失败、11依赖/forkwarnings（92.76秒）。失败是旧Hub
  `test_invalid_and_dangling_manifest_rows_become_diagnostics`和旧链接服务
  `test_serves_pdf_inline`。分别表现为清单整体解析诊断及HTTP404。
- 只提取未修改HEAD `a1d0423835e000bc3c7656d5218dff95c494ece1`到可丢弃开发目录，使用相同
 依赖且明确核对实际import来自该HEAD源码，再仅跑相同2项；均同样失败（1.65秒）。说明它们
  不是本轮新代码引入。此时未修补旧模块或测试输入；随后仅纠正测试输入，结果见下节。

可丢弃HEAD对照目录不是业务样本或交付Vault；用户可见A/B对象仍在test Vault，不把实验放/tmp。
前一轮测试期间uv自动刷新lock内自身版本，已按原字节恢复；本次0.41.3发布批次仅同步
lock中的项目自身版本，不改变任何依赖。

## 0.41.3发布前的独立测试输入纠正

仅修正两个已在干净HEAD复现的旧测试，不改变生产Hub或附件接口：

- YAML flow字符串中的冒号必须加引号，保留相同owner ID、错误hash及dangling诊断断言。
- 原PDF响应fixture显式提供合成Local API attachment locator，并断言真实调用；不再
  依赖本机Zotero或假定扫描storage。通过dataclasses.replace替换frozen runtime的测试
  adapter，清理fixture服务socket。首次fixture误用setattr导致7项setup错误，未作为通过。
- 修正后的两个unit模块共29项通过（3.93秒）；随后完整unit/contract **1829项通过**
  （86.47秒），11条既有依赖/fork warnings。全套未访问正式Zotero/知识库或重跑论文业务。
- 四处版本与lock自身版本同步为0.41.3；安装态点击和人工图片评鉴仍独立待完成。
- 发布版本/eval Schema另行11项通过；Skill quick_validate、受影响生产代码、新测试及
  Local API fixture Ruff、git diff检查通过。系统python缺PyYAML的首次validator启动失败，
  通过临时开发依赖运行原validator成功，未新增产品依赖。旧test_hub_attachments模块的
  两项既有import/UTC lint未顺手修复，不能把此结果称为全仓Ruff通过。

## 发布前历史状态与仍未完成边界

未提交/发布/安装新构建；未手改受管Canvas、未动正式分析、图片asset声明、registry、provider、
PDF或项目文件，未重分析/重跑实验。下一轮产品点击必须先按正常入口安装可识别hotfix，再
仅用同一test单篇成对更新候选；核对确切文件和块，保留旧候选作对照。

图片裁剪充分性、可读性与美观仍需会话明确人工确认；当前图片未canonical归属/提交，项目
资料覆盖授权仍独立待答复。整个G17保持active，不以这次窄修复或合成通过冒充完成。

## 受影响实现指纹

以下SHA-256绑定最新246项测试的代码，便于区分后续修订；不是发布或安装身份。

| 文件 | SHA-256 |
|---|---|
| analysis/models.py | 0d7185f379c4b1e15bd6dcb075119066dd78a0493731959f7288814bb877b874 |
| analysis/complete_reference.py | beb3a399d4a894b34a193113b33cee8eb7a82f100272a144a1c0ff2c29b780ed |
| analysis/commit.py | 1c115827f9250e1d811a36f27e4c96aa0b4e3cd382800365430c16f26f04d299 |
| analysis/updates.py | 330d023a7d3e54df53128d251bab52efaa84a1d3fd1288ea608f6961baa04a4e |
| workflows/knowledge_reproduction.py | dd2bfa2938cf964937f88b68c4f8e998550acaf11e347256fe833a75572c06d1 |
| contracts/analysis-ir.schema.json | 85f84b546523a7c64ce36e9e45139bbd211a15160c5aab691d445f8802456472 |
