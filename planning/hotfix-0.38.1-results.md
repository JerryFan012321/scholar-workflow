# 0.38.1：保留旧图的更新链路

## 已证明的开发结果

对象、输入、步骤、预期和影响见 analysis-existing-update-test-plan.md，并在会话中说明。
使用独立合成 fixture；本轮开发测试没有操作真实 Vault、Zotero 或服务。

- 68项定向测试通过（1.58秒）：布局保留、新节点列对齐、分裂列不静默重排、focused合并、
  三文件CAS、人工冲突、symlink、全图覆盖拒绝，以及metadata公开CLI拒绝/成功/重放。
- 最终完整unit/contract：1579通过，11既有警告，80.34秒。
- 首轮完整回归1578通过/1失败：旧skill路由断言要求只在多篇分析加载batch reference。
  更新为多篇或既有文档对更新的真实路由后全套通过；未降低Canvas或来源要求。
- 变动模块Ruff、skill validator和git diff --check通过。
- 完整五分支模板未修改。版本号、两个plugin manifests和lock一致为0.38.1。

## 可复用的运行接口

analysis stage-update从真实三文件基线保留旧图，只暂存一个对象，并返回完整成对提交请求。
commit拒绝未经保留边界的全图覆盖；旧节点位置/样式、自建图元和允许metadata不被重排。

analysis acknowledge-canvas-metadata只接受能精确证明的新增空frontmatter metadata；
通过现有provider CAS登记Canvas新物理hash，返回独立回执及next_request，不改Vault文件。
文字、布局、未知内容、归属和基线变化不能用此入口接纳。校准不冒充分析内容提交。

## 尚未证明

此时尚待正常runtime-only发布、安装身份核验，以及安装版在test唯一V-JEPA2对象上
校准、暂存、成对提交与回执登记。真实两点证据修订仍未提交，不用开发测试冒充安装态成果。
GUI美观、编辑/点击与逐项科学支持仍独立待人工评鉴；未合并main、未改正式库或服务。
模范项目既有context覆盖仍等待其独立业务授权；本切片不等于第一阶段全部完成。

## 后续安装态结果（覆盖上述待执行状态）

正常runtime-only发布安装完成：source00450977342a750778c621f7cce9f57a634fef29，
runtime d6752da419c2cde8bfcfe99d369552a444fb4c11；CLI/module/dist/Codex cache均0.38.1。
public metadata校准只记Canvas新hash；stage-update单篇validated、零修复/诊断；
commit-bundle三文件committed，apply-change-set登记三项产物，commit回执重复查询完全相同。
实际check为69内容、106节点、105边、五分支，原生后台加载106/105且69正文反链解析。
34其他claims逐项不变；105旧节点几何/样式及104旧边保留，metadata保留。
原文物理p5的图3和p14表2只读核对；未将引文匹配当成全篇科学支持评鉴。

最后打开再关闭图发现编辑器重新编码：物理Canvas从8baf7daf变c8e2c97b；完整JSON完全相同，
canonical编码匹配登记的8baf7daf，MD/sidecar未改。provider因此出现物理CAS漂移，不伪称
链路稳定完成。另开0.38.2精确编码校准，不改回文件、不放宽布局/内容证明。

可读入口在同一论文目录的复现/证据修订-0.38.1/修订说明.md；Obsidian后台activeFile确为
该新MD，4入口解析。人工点击/编辑/审美仍待确认。registry与Fieldhash和既有身份保持，
正式Vault/Zotero/PDF/服务/main/项目既有清单均未改。

## 0.38.2：编码缺口闭环

69定向与完整1580通过（80.87秒，11既有警告），Ruff/skill/diff通过。
正常发布安装source1a77d297299fa34bc36f8236afd9d61141d82b5a、runtime
7b6f89432b03619224e7d7907c66117c99b6d6d5；CLI/module/dist/direct_url/Codex cache一致。
public校准使用明确登记旧hash8baf7daf和当前三文件/provider版本，证明完整图canonical
编码精确匹配旧登记，只记当前物理Canvas hashc8e2c97b，没有写论文三文件。
原生打开新图再关闭到修订说明后，三文件与校准输入及provider全部一致；重复校准回执
完全相同。实际check通过69/106/105，最新检查与独立输入/回执在同一复现目录中。

0.38.1历史提交回执没有改动；其Canvas字节变化通过独立校准回执追溯，不编造物理hash
恒定。回退可固定安装0.38.1 runtime d6752da，不自动删除资料。没有服务切换或main合并。
人工点击/美观/编辑与逐项科学支持仍待评鉴；项目context与便携Canvas清单的后续能力
尚待推进，本次不宣称第一阶段全部完成。
