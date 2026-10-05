# 0.39.0 知识归属复现 hotfix

## 范围和独立测试输入

交付同一能力批次的reproduction-plan、restore-plan/restore、公开package schema及运行说明。
不改论文格式/生成器/Canvas；原V-JEPA2完整摘录不重新分析。main、正式Vault、项目和服务不动。
用户已有的分析审阅计划和两个quotation-preview文件不进入本次提交。

合成测试：明确单篇Source复制到新根、新host registry；身份和全部字节守恒、独占创建provider、
Local API成员/PDF校验、冲突、中断续接、输入/journal/根变动与reader交接。完整unit/contract
1676 passed、11既有warnings（84.43秒），四变更Python文件Ruff及diff空白通过。
此次版本同步后manifest/runtime identity、CLI及归属定向回归71 passed（2.06秒）；
skill quick_validate、diff空白通过。不重跑真实业务。

## 正常发布与安装（已执行）

分支codex/hotfix-project-context；版本0.39.0。源码907c3f922ff805359ab55f3ade8a3249346bd640，
runtime-only release63a29f12ab47616d8cc38abec9d04738241110c0，由既有make-release脚本
从干净独立clone生成。两分支均已推送，main未合并。
release含242个runtime文件，不含planning/dev-guide/tests/evals或根规则；限定私人路径和
真实样例ID扫描无命中。pipx正常固定runtime SHA安装，direct_url commit_id和requested_revision
均吻合；实际executable/module/distribution为0.39.0，public --version也为0.39.0。
Codex正常marketplace upgrade/add返回0.39.0缓存，不手改缓存，不用临时venv替代安装。
回退0.38.3 runtime8f2cdacbabb2d7b963ae805e0fbc4bae9d435a6a；回退不自动删业务文件。

## 单对象安装态复现（已执行）

唯一真实输入是test Vault当前模范知识目录-0.36.0里的V-JEPA2已登记Source/provider。
新根为同一test Vault内独立“模范知识目录-0.39.0-复现”；仅复制导出的明确文件集合，
不复制PDF/秘密/旧主机provider。使用独立SCHOLAR_WORKFLOW_HOME模拟新主机，复现记录
另放所复制Source之外，保持批准文件read-set。旧注册表/源provider/原文件前后hash核对。

执行步骤：安装态只读导出→明确文件复制→existing-source预览和附着→restore-plan审阅并执行→
同摘要重放→check-bundle与全inventory hash核对→native knowledge open展示正文/Canvas。
预期：稳定身份保留、主机绑定指向新根、旧回执不导入、所有文件字节不变、回执幂等。
影响：仅新增test复现目录、记录及隔离主机状态；Zotero/正式资料/服务不写入或启动。

系统接受open请求不代表GUI可见或人工评鉴。需要人判断时，必须在会话明确对象、打开方法、
观察点和待确认项。记录本轮实际结果，不重复已认可的布局评审，也不把其当科学全项通过。

## 实际自动结果

- 导出明确8文件：两份入口说明、Paper.md、分析Markdown、Canvas、sidecar、fields.yml和artifacts.yml。
  没有复制PDF、旧host provider、旧回执、秘密或整库内容。
- 注册预览conflicts/unmapped/external-managed均为空；附着只在隔离host registry登记完整既有Source。
  Source/Field/resource/artifact identity保留，Field标题保留原版本字样，不为了展示改写manifest。
- restore返回ownership-restored；provider绑定新根，旧receipts为空。content_rewritten、backup_verified、
  human_verified、scientific_review_verified及reproduction_complete均false，不能说整阶段已完成。
- 同摘要重放回执字段值完全一致。目的地重新导出package digest与原导出完全一致：
  sha256:a35468d75229ef54c7a6b859068ec8f1f770665595520982364beb616642a392。
  归属恢复approved digest：ead7baca1134e4e5994351973fb1321a3d867b5abf91ba5138c69d5cef84aacf。
- 全部8文件hash一致；旧论文三文件、原manifest、主机registry、原provider和PDF等8个保护对象
  在复制、恢复、打开后hash保持不变。新正文d02be6fc、Canvas8baf7daf、sidecar047f535d。
- 安装态analysis check-bundle：conformant、findings为空，IR5、whole/zh、五分支、
  69条内容、106节点/105边。结构检查不认证科学来源或真实reader点击。
- 保存的ZotFlow Vault ID与实际包含Source的test Vault相符，reader_launch_verified仍false。

## 实际展示与人工交接

公开knowledge open请求正文/Canvas成功；原生CLI随后核实active view/path精确指向新目录。
正文DOM读到第一处连续完整原文句子，Canvas backend载入。首次“解析树实机.png”捕获的是Markdown；
后续“解析树实机-确认.png”捕获Canvas且缩放过小。“复现说明实机.png”仍显示Canvas，和当时
backend记录的Markdown/preview不一致。原生窗口检查随后明确报告Mac锁屏，自动解锁不可用。
因此三张截图均可能陈旧，全部排除出本轮GUI/视觉验收证据；不能用backend载入证明屏幕实际更新。
未修改已认可的布局来制作截图，待用户解锁后再检查当前窗口，不重复归属恢复或论文分析。

test中的“复现记录-0.39.0/使用说明.md”提供新副本入口；机器导出、附着/恢复方案与回执、
幂等回执、目的地再导出、最终check、provider和hash另存该记录目录，不淹没分析正文。
本轮请用户只判断新摘录必要语境、来源链接与新副本反链，不重做布局设计。尚未收到本轮明确
确认，不将安装、打开或hash一致冒称人工验收。G17仍active；项目资料整合与其他阶段交付另行推进。

本轮仅结果说明更新后的定向检查：evals JSON结构10 passed（0.02秒），diff空白检查通过；
“使用说明.md”的正文、Canvas、资料笔记三条wiki链接经Obsidian实际解析到新目录中的精确文件。
没有重新运行开发全量测试或真实论文分析。用户原有三个规划改动不进入本轮记录提交。
