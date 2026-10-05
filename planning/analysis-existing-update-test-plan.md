# 已有分析的成对更新：独立测试方案

## 问题与范围

安装版0.38.0的真实V-JEPA2两点证据修订在全新布局下conformant，但保留既有布局时出现
`canvas-level-alignment`：新增节点沿用了新列坐标，旧节点保留原坐标。不能用全图重排绕过。
canonical内容仍未改。原生打开预览时Advanced Canvas自动添加允许的metadata；节点/边不变，
Canvas物理hash已变。公开batch暂存目前没有保留原图的更新入口，commit也须拒绝丢弃旧图。

修订仅在analysis层：新增节点采用同层唯一的已有左边缘；不修正分裂的人工列、不移动旧节点、
不放宽交叉/遮挡规则。新增公开stage-update复用既有commit请求、更新引擎、batch状态和CAS提交；
不新建Hub、状态事实源或自动迁移。它只写阶段产物，返回后续成对提交请求。

## 先行固定输入与预期

| 对象/输入 | 操作 | 预期 |
|---|---|---|
| 合成同层图：旧列420、新渲染列600、新节点600 | 合并旧布局 | 新节点420；全部旧坐标、样式及独立人工节点不变 |
| 合成分裂列420/450 | 合并 | 不静默对齐旧节点；冲突继续由conformance拒绝 |
| 旧IR v1 | 合并 | 不把树状同层规则推广到旧投影 |
| 既有v5合成包，新增一个结果子项 | stage-update | 只写受控阶段；输出完整合并IR及可直接commit的请求；原三文件hash不变 |
| 原文/生成节点内容被人工改动 | stage-update | 成对冲突；不创建成功批次、不覆盖原件 |
| 过期base hash、符号链接或不完整三文件基线 | stage-update | 拒绝；不读取越界路径、不写canonical |
| 相同batch ID但不同更新基线 | 再暂存 | 身份冲突，不复用旧成功 |
| 既有人工布局，普通batch全图重排后提交 | commit-bundle | 拒绝丢弃布局，原件不变 |
| 同对象经stage-update保留布局后提交、再回执查询 | commit-bundle | 三文件提交一致、回执幂等、provider CAS仍有效 |
| provider登记后仅metadata或安全布局变化，调用者提交新物理hash | commit-bundle | 仍拒绝provider hash漂移，canonical与provider零写入；不能用sidecar语义hash替代物理CAS |
| 仅新增合法metadata，去掉它后精确匹配provider旧图 | acknowledge-canvas-metadata | 原三文件字节不变，仅通过现有provider CAS记新Canvas hash；有独立回执，重放不写 |
| 节点文字/坐标同时变化、非空frontmatter、过期请求 | acknowledge-canvas-metadata | 拒绝，不写provider或canonical；不能接受未证明的内容/布局变化 |

## 新发现的原生保存边界

只读事实核验：当前Canvas为ef814cab，去掉新增metadata后按canonical格式编码恰为
provider登记的006787d2；MD/sidecar未变，105节点与104边完全相同。没有执行更改provider。
普通stage可能通过，但当前commit仍必须拒绝这项provider物理hash漂移。允许metadata与
允许绕过provider CAS是两件不同的事。

当前补受控原生保存校准入口：以旧provider实体/版本、真实三文件字节和baseline为输入，
只接受新增空frontmatter的合法metadata，且去掉metadata后必须精确匹配旧provider图hash。
验证在已登记Source、provider和Vault锁内完成，复用现有provider CAS/回执；不新建事实源。
现有裸apply-change-set不读取论文文件，不能单靠调用它冒充此证明。不手改provider或图，
不放宽一般hash检查。校准返回最新provider版本的next_request，后续使用它暂存，
不手工查找或修改版本。68项定向测试及1579项完整回归已通过；安装态结果单独记录。
不宣称真实两点提交已完成。

## 命令、影响与可见产物

按最新全局测试规则，说明后先运行新的更新合成测试及现有v4/v5更新、batch、commit定向回归；修复后执行
`pytest tests/unit tests/contract`。所有开发测试仅临时fixture，无真实库操作。源码检验不等于安装。

正常发布安装可辨识hotfix后，只复验当前test Source内V-JEPA2：图3补物理第5页入口，
机器人数值保留作者陈述，原有泛化边界移到独立推断子项；其余34 claims及所有论述逐项守恒。
一次新更新批次，精确三文件/provider CAS；失败保留当前canonical，不重复整篇科学分析。

交付是同一论文的更新正文、可编辑Canvas、分离的输入/回执及简洁修订说明。GUI/点击/编辑
仍需人工评鉴；不改项目清单、代码、Run、正式Vault、Zotero或服务，不合并main。
