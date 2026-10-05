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
