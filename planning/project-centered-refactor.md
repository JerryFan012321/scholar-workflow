# 项目中心资料整合与职责重构

> 状态：Accepted / Stage A 已通过1313项源码回归，0.31.0 hotfix 已发布并正常安装，2026-10-02。
> 人工与安装态功能验收待做；以下未测试/未发布措辞为实施前规划记录，不覆盖当前状态。用户批准按项目中心、
> 原生工具优先的方向重构。独立context/schema/只读CLI和首批公共模型提取已实现，仍需独立测试审批。
> 代码与文档变更不等于测试、安装或人工验收通过；本批未运行测试、未访问或迁移真实 Vault/项目，
> 未关闭服务、删除历史线程、发布或安装。当前安装态与开发树须分别报告。

## 1. 产品定位

Scholar Workflow 利用现有工具维护科研项目的完整资料上下文，让人和 agent 理解项目、找到依据、
调用代码、追溯实验并查看成果，避免资料分散和重复维护。中心对象是科研项目，不是工具菜单。

- 集中展现，不等于集中存储：Zotero 留住论文/PDF/正式批注，Vault 留住可复用分析与知识，
  项目留住源码/项目正文/实验档案，Notion 留住人工管理视图或单向简化投影。
- 建立关联，不等于自动同步：Project 保存明确的导航与上下文引用，不接管外部正文。
- 整合内容，不等于接管工具：cmux、外部 Codex、Obsidian/ZotFlow 和 Notion 保持原生接口、配置与历史。
- 不强制新建首页。既有 README、目录或笔记可作为人工入口；CLI overview 输出可读 Markdown，
  用户需要时显式保存为自己的文档，不以架构要求强制生成另一份正文。

Hub 前端、内置 Codex 模型配置/线程控制/长期 worker 不再是产品发展方向。不是设计 Hub v4，
也不是通过跳过安全约束继续旧执行路径。旧代码未退场前只维持兼容与安全。

## 2. 权威与职责

| 责任层 | 持有的事实/能力 | 不持有的责任 |
|---|---|---|
| Project | project_id、布局/profile、薄资料关联、项目正文、Run/Attempt/Target/成果档案 | 外部知识正文、Zotero批注、Codex线程控制 |
| Knowledge | 可复用原子资源、核心/导航文档、附属产物与 owner、Source/Field与关系、安全更新 | 训练调度、项目执行权限、网页运行状态 |
| Analysis | 论文 AnalysisProfile/IR、已验收 Markdown/Canvas 模板、行内证据与 conformance | 全知识库/Source注册、工具菜单和HTTP授权 |
| Adapters | Zotero Local API、Obsidian/Notion/native URI、cmux等具体外部接口 | 判定项目/知识内容结构、另建控制面 |
| Workflows | 按用户范围组合上述能力并返回结果/失败回执 | 第二份模型、隐式事实源或扩权 |
| CLI/agents/skills | 参数入口、结果契约、工具/权限边界和可读呈现 | 核心业务重复实现、模型内部推理步骤 |

业务模型在所属核心层定义一次。迁移期间旧 import 可用薄 re-export/facade 维持兼容，但不得复制模型。
核心层不向上依赖 HTTP、UI、task store、workspace registry 或 installed-service 生命周期。
Adapter 可消费所属核心契约，workflow 可组合核心与 adapters，CLI/agent 调用 workflow/核心接口。
这是目标依赖规则，不是对全部旧实现的完成声明：本批先提取Knowledge对象/catalog模型、Obsidian文档
契约与Source/Field职责，并保留旧import兼容；Analysis提交/批注workflow仍有 `hub.zotflow` 依赖，
文献树CLI仍更新Hub catalog，Field transaction CLI仍调用受管Hub HTTP。它们属于后续最小切片，
本批项目context/overview不经过这些调用链。不能据此删除旧包或停止服务。

## 3. 项目资料清单：独立、薄、显式

项目根可选 `project-context.json`，与 `project-layout.json` 分立：

- layout 继续 schema 2，仅有便携项目身份、源码/profile/addon契约；不塞文献关联。
- context 使用 schema 1，`project_id` 必须匹配 layout；创建/更新由明确请求触发，普通初始化不静默补写。
- 关联目的属于项目；被引用对象的正文、owner与主存储不变。
- 删除关联不删除外部对象；缺失/冲突只报告，不同步、搬迁、复制或级联操作。

本批冻结形态：

```text
ProjectContext {
  schema_version: 1,
  project_id,
  title,
  summary,
  language?: en | zh, // 默认en；呈现标签、状态与诊断使用同一语言
  entries: [{
    entry_id,
    kind: code | paper | analysis | note | experiment | result | other,
    title,
    purpose,
    ref
  }]
}

ref = project-file {
  relative_path,
  commit?  // 可选完整40位commit，仅为显式声明，本批不验证Git历史
}
    | external-resource {
  provider: zotero | obsidian,
  resource_id,
  uri?     // 可选稳定 zotero:// 或 obsidian:// 阅读入口；不是对象身份
}
```

禁止秘密、主机绝对路径、动态端口、loopback入口、进程 action ID 和任意执行配置进入清单。
内部文件只以项目根下安全相对路径读取/诊断，拒绝路径逃逸与 symlink 不安全入口。
文件名相同不证明归属；条目 ID 和明确引用由用户/agent 给出，不通过扫描目录自动猜测。

清单可以引用实验报告和结果，但不代替 Run/Attempt/Artifact manifest；登记了 result 不证明实验成功、
内容存在、promotion完成或 backup verified。外部URI是原生导航，不改变既有秘密和文件授权边界。
provider/resource身份与阅读器投影分离：Zotero对象可以使用已登记Vault的 `obsidian://zotflow` 阅读入口。
本批只接受已知阅读endpoint/query语法，不执行URI；语法合法不证明URI与对象身份匹配，仍标unverified。

## 4. 本批只读入口与可见结果

本批新增最小入口：

```text
scholar-workflow project context-template --project-root PATH [--language en|zh]
scholar-workflow project validate-context --project-root PATH
scholar-workflow project overview --project-root PATH [--json] [--language en|zh]
```

- template 只向 stdout 输出绑定项目身份的空模板，不写 context、README或注册记录。
- validate 只读检查清单/schema/项目身份与受控本地locator，不启动服务或外部应用。
  locator检查仅指安全相对路径/阅读URI的声明语法；本地路径存在性由overview诊断，
  validate成功不证明引用对象实际存在或可打开。
- overview 展示项目名称/摘要、代码入口、论文、分析笔记、实验与结果；链接附近说明关联目的与状态。
  Markdown为人类版本；JSON用于机器消费，二者不保存第二份正文。
- context language 默认en，template 可明确选择en/zh；overview 可覆盖显示语言而不改清单。
  可见标签、状态和诊断保持同语种，不改用户原始标题/摘要内容，不用机器枚举代替人类状态说明。
- 本批不联网、不给外部来源做伪核验：Zotero/Obsidian引用是 `unverified`；本地条目可报
  `missing`/`unsafe`，已登记与已解析不可混称。无context/冲突/错误清单须给出可读诊断。
- 不要求 Hub、workspace、Codex配置或Source registry 存活，也不通过资料登记启动训练/CLI/Codex。

这只是最小关联/呈现切片。完整项目图谱、跨提供者解析、任意格式预览或新工具登记不在本批默认范围。

## 5. 分批重构与完成标准

### A：定位、规则与最小独立项目入口（当前批）

交付：HANDOFF、G16/INV59–INV61/NG21–NG22、WI-054和当前规格；context schema/model、薄CLI与
合成项目样本；只提取本批确实需要的共享模型/原生文档契约，旧导入保留兼容。

完成标准：人无需Hub即可看到一个项目的明确资料关联；schema/身份/安全路径和状态可复现；
已验收分析框架不改、layout schema不改；剩余Hub反向依赖如实列出。实现完成不等于验收完成。

当前状态：context/schema、三条只读CLI及上述共享契约提取已有源码；尚未执行测试或安装候选，
不能宣称产物有效、人工可读性通过或外部阅读入口可用。后续先展示独立输入、预期输出和影响范围，
获批后测试；不用旧Hub的真实任务或整库迁移作为本切片的门禁。

### B：Knowledge与Analysis剩余职责拆开（后续切片）

本批已经把资源/核心文档/附属owner、catalog模型、文档契约与Field实现归到Knowledge；
后续继续分离剩余内容状态apply/提交路径与阅读器adapter，让Analysis只持有分析IR/渲染/更新契约。
复用既有模型/CAS/journal，保留旧import适配，不搬真实文件或重渲染真实论文以证明代码搬家。

完成标准：选定内容入口在不启动HTTP的条件下读写受控合成对象；实际更改路径仍具冲突保护与恢复；
普通内容工作不再因Hub catalog更新失败而被伪记为全失败。未覆盖的调用链保持明示兼容。

### C：原生工具组合与Hub安全退场（独立批准后）

把原生阅读器/批注/相关资料定位放到adapters/工作流，直接使用cmux与外部Codex；不再建任务页。
先拆内容对HTTP/service依赖，再逐项处理可识别的旧service、worker状态及兼容入口。

完成标准：没有把必需文件安全原语或知识身份随 `hub/` 一刀删除；用户明白哪些旧入口退役，
旧进程仅在身份确认及明确授权后停止，外部Codex历史和知识正文保留。

### D：安装态单项目验收与后续真实迁移（独立范围）

独立hotfix候选用正常发布/安装途径部署，标明版本/source SHA/build和回退方式；验收通过才合并main。
一个受控项目即可验证设计，不反复整库分析。真实Vault/项目迁移按各自当前字节预览、审批与恢复门禁
另行执行；备份介质/保留策略/恢复演练仍归WI-041，recovery snapshot不冒充verified backup。

## 6. 独立测试与人工评鉴

本批只准备测试，不运行。批准请求应给出：一个合成项目layout/context、匹配及错误project_id、
本地存在/缺失/越界/symlink、重复entry ID、禁止URI/秘密字段、外部unverified引用等输入；
预期stdout Markdown/JSON、退出状态、项目字节零变化和对旧分析/profile/archive的定向回归范围。

人工评鉴必须在会话中另行写明：如何打开同一项目overview，能否看懂项目目标、资料关联目的与状态，
能否在原生工具找到论文/分析并追溯一个实验报告；对不联网未核验链接不声称已点击通过。
保留已通过的V-JEPA模板/Canvas/原文页链验收，不把它当成本项目overview或真实迁移验收。

## 7. 历史门禁与边界

- G10/G14/G15及Hub UI/worker专属残余门禁退役，标retired，不改成pass。
- 仍存在的兼容HTTP/执行/文件写路径继续受原安全策略保护；产品退役不等于安全规则失效。
- 本文更新P-D10/INV46/NG14中的旧禁止引用决定：明确导航引用允许，自动同步与双真源仍禁止。
- 已发布Project v2的dataset/env/profile、Run/Attempt/Target、promotion/backup语义保持不变。
- 论文参考图完整框架、可编辑Canvas、一篇一目录、行内证据与原文反链继续有效。
- 真实JEPA/Field搬迁、其他Vault或项目迁移、服务切换、安装发布及verified backup均未因本批获得完成证明。
