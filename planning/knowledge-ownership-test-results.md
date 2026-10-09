# 正式归属只读解析：合成验证结果

日期：2026-10-09。分支：`codex/hotfix-knowledge-ownership`。
基线：0.41.8源码 `71a9f7bc7722d449cb2866a9039b8df35795746e`；0.42.0本地候选准备，未发布、未安装。

## 结论与边界

57项新归属用例和138项必要回归全部通过；两处代码规范修正后，195项联合复跑全部通过。
这证明本开发切片在合成声明下的只读解析、失败状态、安全边界与默认兼容，不证明安装态、
真实文库归属、阅读器正确显示、科学支持或完整G17完成。

用户在会话批准本轮合成范围。输入与手写预期先于实现，保留在
`tests/fixtures/knowledge-ownership/EXPECTED.md`及`DEFAULT-OVERVIEW.md`；没有用产品输出回填。
计划见[独立测试计划](knowledge-ownership-test-plan.md)。

## 各轮实际结果

| 轮次 | 范围 | 实际结果 |
|---|---|---|
| 1 | 新归属契约用例 | 57 passed，4.35秒 |
| 2 | 项目总览/候选、知识契约/登记、eval schema | 138 passed，1.51秒 |
| 3 | 5个改动Python文件Ruff | 不通过：ISC004、TRY004各一项 |
| 4 | 最小规范修正后Ruff | All checks passed |
| 5 | 专项及必要回归联合复跑 | 195 passed，1.88秒 |
| 6 | 结果记录更新后的eval schema复查 | 10 passed，0.01秒（195中的既有用例） |

最后`git diff --check`通过；归属核心导入检查确认只依赖标准库及Pydantic，无Hub/
Analysis反向依赖。workflow按既有职责组合provider validator与project模型，不新增事实根。

195是不同用例的总数，复跑不计为另一批新增测试。耗时为pytest报告值，首次环境准备不含其中。
本工作区通过离线uv创建开发`.venv`并构建当前源码；这是合成测试环境，不是正常插件安装。
没有下载网络依赖、启动应用或服务、修改已安装插件，也没有写真实Vault、Zotero、项目或provider。

### 失败与最小修正

- ISC004：人类存放路径字符串在列表内隐式拼接，补括号明确表达；输出内容不变。
- TRY004：非法YAML键改用`yaml.constructor.ConstructorError`，仍由既有YAML异常分支报告
  声明不可核验；不放宽输入、不改变归属或文件授权策略。

没有产品测试失败，未改独立预期或为通过而放宽断言。
运行前静态审阅发现的祖先symlink及主owner提示遗漏，不冒充本轮运行失败。

## 通过意味着什么

| 输入情况 | 实际测试确认的结果 |
|---|---|
| 唯一论文/分析/Canvas/core声明，含根Field`.` | 返回同一显式主归属；分别定位各文件 |
| artifact-only sidecar | 从声明取得owner；JSON正文读取被测试守卫禁止 |
| 两项目复用同一对象 | 指向同一owner，不复制、不新增关系权威 |
| 两Source声明同一主归属 | `conflict`，不选择第一个；已有冲突不被其他不完整声明掩盖 |
| 禁用/不可读/不一致/读中替换的声明 | `incomplete`，不误报全局唯一 |
| 声明全集中没有ID | `not_found`，不以同名或reader URI猜归属 |
| 目标或主owner文件缺失 | 保留声明归属，分别显示`missing`；不是对象身份消失 |
| symlink、越界、目录或FIFO | 不跟随/不读取非普通文件，不挂起；报告不安全或声明不可核验 |
| 原阅读入口尚未实际打开 | 始终`unverified`；归属核验不冒充阅读器验收 |
| 默认总览 | 不读registry；JSON保持，Markdown匹配独立手写golden |
| 可选总览 | 原引用/状态不变；只增加归属结果，可读正文不暴露机器ID或绝对根 |

产品调用期间有精确声明路径读取白名单、正文读取/工具启动/文件变更守卫；每项保留
输入文件与目录集合。读中替换仅由显式fixture hook模拟，产品无写入例外。

## 可复现命令

在本hotfix工作区运行；仅使用pytest合成临时目录。

```bash
rtk proxy uv run --offline --with pytest python -m pytest tests/contract/test_knowledge_ownership.py -q --tb=short

rtk proxy uv run --offline --with pytest python -m pytest tests/unit/test_project_context.py tests/contract/test_project_context.py tests/contract/test_project_context_cli.py tests/contract/test_project_context_candidate_cli.py tests/contract/test_knowledge_contract.py tests/contract/test_knowledge_registration_cli.py tests/unit/test_evals_schema.py -q --tb=short

rtk proxy uv run --offline --with ruff python -m ruff check src/scholar_workflow/knowledge/ownership.py src/scholar_workflow/workflows/knowledge_ownership.py src/scholar_workflow/project/context.py src/scholar_workflow/cli.py tests/contract/test_knowledge_ownership.py

rtk proxy uv run --offline --with pytest python -m pytest tests/contract/test_knowledge_ownership.py tests/unit/test_project_context.py tests/contract/test_project_context.py tests/contract/test_project_context_cli.py tests/contract/test_project_context_candidate_cli.py tests/contract/test_knowledge_contract.py tests/contract/test_knowledge_registration_cli.py tests/unit/test_evals_schema.py -q --tb=short

rtk proxy uv run --offline --with pytest python -m pytest tests/unit/test_evals_schema.py -q --tb=short
rtk git diff --check
```

## 仍未通过的独立交付

- 正常hotfix提交、打包、发布和安装，以及安装身份核对；当前命令不可被描述为已安装功能。
- 安装后仅对当前V-JEPA2和一个模范项目进行零写入总览，再明确展示人类导航评鉴对象、操作和标准。
- 不同ID映射同一论文的跨Source登记查重、Field引用写入、归属迁移；这些不在本切片内。
- 完整科学支持、全部阅读入口和G17阶段验收；已有Canvas、图片及折叠体验批准保持，不重做。

上述首轮195项仅属定向验证。随后发布前完整回归结果如下；始终未运行真实整库业务。

## 0.42.0发布前合成回归与本地包准备

四处版本及lock中本包版本已同步0.42.0；依赖及其他lock记录逐行不变。
本轮只做同一切片的发布准备，没有新的业务功能或论文输出修改。

| 检查 | 实际结果 |
|---|---|
| 完整现有unit/contract | 2092 passed、11 warnings，97.00秒 |
| 改动Python Ruff | All checks passed |
| 离线lock检查 | Resolved 24 packages，3ms |
| 开发公开`--version` | scholar-workflow, version 0.42.0 |
| 开发公开`project overview --help` | 两个归属选项均显示，原选项保留 |
| diff | 通过 |

11项为SWIG及多线程fork的既有DeprecationWarning；没有失败、忽略或跳过的用例。
这是合成单元/契约验证，不是正常产品安装或真实阅读器验收。

```bash
rtk proxy uv run --offline --with pytest python -m pytest tests/unit tests/contract -q --tb=short
rtk proxy uv lock --offline --check
rtk proxy uv run --offline scholar-workflow --version
rtk proxy uv run --offline scholar-workflow project overview --help
```

记录更新后的runtime-version及eval-schema11项再次通过（0.06秒）；这11项是全集中的
重复核对，不另计新增用例。首次RTK多路径diff参数转发报bad revision后改用raw proxy；
首次临时构建目录的父目录尚不存在，创建明确dist目录后成功。二者是操作观察错误，
不是产品测试失败；未因此重复论文或实验业务。

## 本地发布产物（已构建，未推送安装）

| 身份 | 实际值 |
|---|---|
| 版本 | 0.42.0 |
| 分支 | codex/hotfix-knowledge-ownership |
| 确定source SHA | 809ebf78a28233050eb4662b6ae5de2708565729 |
| 隔离clone的runtime SHA | aeffdea8ca2a1f99eafc2f47df248bc9d0d94127 |
| 当前远程release/上一正式版本 | 1a85790740dee9735112d57e7f19346259a2a21a / 0.41.8 |
| 本地目录 | dist/0.42.0-local.SSlrbj |

先本地提交24个明确文件、确认干净source，再在上述独立clone读取真实远程release历史，
按既有make-release.sh生成本地runtime。旧release为新runtime祖先，源worktree的
release/main引用未因构建改变，未推送或创建远程tag。产物记录随后更新，仍以表中的
固定source构建，不用记录文件的新工作区状态冒充其source SHA。

| 包检查 | 实际结果 |
|---|---|
| runtime archive | 246文件、16个顶层入口，与固定source所有对应文件逐字节相等 |
| runtime开发边界 | 无planning/dev-guide/tests/evals/AGENT/CLAUDE |
| 新模块 | ownership模型和workflow均已进入runtime及Python包 |
| wheel/sdist内容 | 104 Python模块＋3静态文件与固定source逐字节相等 |
| 身份与入口 | 四处版本、wheel METADATA和console entry point一致；包`--version`为0.42.0 |
| 包帮助与导入 | 两归属选项显示；归属两模块导入成功，实际模块来自隔离uv wheel环境，不是源码或pipx |
| 私密模式扫描 | 指定个人根、临时路径及令牌模式无匹配；不据此宣称检出所有可能秘密 |
| 正常安装核验 | 显式pipx CLI与Codex cache manifest仍0.41.8，未修改 |

首次宽泛`sk-`模式匹配历史说明中的`ask-collection-before-write`，核对为误报；增加
词边界后无匹配，没有为去掉误报修改产品文档。隔离构建的verify-package.py只读
核对Git、tar、wheel、sdist，预期固定于源码SHA与runtime manifest；没有产品写入。

| 产物（相对本地目录） | SHA-256 |
|---|---|
| scholar-workflow-0.42.0-runtime.tar | 7f930a482cce08e37391e95ef471ee4ec366924f670e7f317e657c532f094c6e |
| packages/scholar_workflow-0.42.0-py3-none-any.whl | 7e0ffdf3f2ce1bf2729c5f188a326de3461898834e46970e57c882d54379fc13 |
| packages/scholar_workflow-0.42.0.tar.gz | 0f9368d5d25e0b912b5bd053a043d303aab753680975c12f9a29c575833bccdb |

安装包检查仅用`uv --offline --no-project --with <wheel>`的隔离环境和公开version/help/
module import，不是正常插件安装，不启动Hub、Obsidian、Zotero、Codex或cmux。
下一步须明确正常推送/安装授权，之后只读当前V-JEPA2及一个模范项目并展示导航结果；
人类评鉴在会话另行明确对象、操作及标准。main及真实正文不变，已有Canvas/图片/
折叠体验通过结果保留，完整G17仍未完成。

## 实际解释器兼容与回退身份收尾

正常pipx使用Python3.14，其0.41.8 direct_url仅提取vcs身份字段后核对：
commit_id与requested_revision均为`1a85790740dee9735112d57e7f19346259a2a21a`。
三个0.42.0产物重新计算SHA-256，与上表完全一致，没有重新构建或换包。

固定同一wheel在独立uv环境选择Python3.14.5，复验原57专项＋138必要回归＋1条
runtime-version，共196 passed，3.87秒。它们是2092全集中的已有用例，不加算测试数量。
公开模块路径核对确认来自隔离wheel site-packages，不是开发源码，也不是正常pipx。
普通venv、插件缓存、真实资料和服务不变。离线uv曾提示rpds候选需要registry下载，
随后使用离线可用依赖完成隔离环境；未改为联网，不把该提示当产品测试失败。

```bash
rtk proxy uv run --offline --no-project --python <normal-python-executable> --with <fixed-0.42.0-wheel> --with pytest python -m pytest tests/contract/test_knowledge_ownership.py tests/unit/test_project_context.py tests/contract/test_project_context.py tests/contract/test_project_context_cli.py tests/contract/test_project_context_candidate_cli.py tests/contract/test_knowledge_contract.py tests/contract/test_knowledge_registration_cli.py tests/unit/test_evals_schema.py tests/contract/test_runtime_version.py -q --tb=short
```

只读本机pipx帮助确认：reinstall复用原spec，不能用它隐式切换固定Git runtime；
install支持--force和VCS spec。未来经授权的正常更新/回退以明确runtime SHA作为spec，
不用临时venv、手改cache或源码PATH代替。这是入口核实，安装和回退命令本轮都未执行。
Codex仍走README中的正常marketplace/add入口；执行前按当时真实CLI能力核实，
不承诺未核实的SHA pin参数或修改既有marketplace注册。本轮没有调用Codex更新。

收尾记录在本地提交；不改变固定候选source/runtime，不推送、不安装、不合并main。
记录commit的HEAD与809ebf7不同不能被当作候选build source；后者由包字节校验固定。
