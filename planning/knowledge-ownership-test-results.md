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

后续本地构建必须固定source SHA并沿用既有runtime manifest。包身份、hash及边界检查
只在真实生成后记录；不提前称已构建、已推送或已安装。main和真实资料保持。
