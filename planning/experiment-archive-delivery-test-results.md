# 实验交付修正：开发验证结果

日期：2026-10-19。输入与预期先写于experiment-archive-delivery-test-plan.md；所有执行
仅用pytest合成目录，没有访问服务器、正式项目、Vault或Zotero。

## 已完成的开发增量

collected新增重复`--require-run`，要求明确child；缺的所选Run列入required_runs.missing，
无效/pending档案保留原诊断。清单不完整时JSON为partial、打印完整输出后exit6；正常
空库查询及原JSON/exit行为保持兼容。清单只是调用范围，无新增registry或写操作。

共享project-management明确执行、接收与分析交接，轻量原始档案须本地可读，较大产物
可只留manifest。两skill的完成标准和双语说明均指向该唯一契约，不改变review只读权限、
论文Canvas/正文规范、六节PROJECT或同表比较。

## 实际测试与限制

- 首次调用项目uv环境缺pytest，runner未启动；改用临时`uv run --with pytest`运行，
  未增加产品依赖或修改已安装环境。
- 首轮9项中6失败、3通过：新清单选项尚不存在；随后强化三项非法输入的具体错误断言，
  不以同为exit2的未知选项错误冒充输入边界通过。
- 实现后9项全部通过，2.55秒：报告-only/空目录/漏Run/损坏配置/完整接收/旧generic/非法
  范围分别取证；输入父子文件集合和字节保持。缺档案检查禁止工具子进程与宿主配置读取。
- collection/management/CLI兼容/review fixture/eval结构共113项通过，4.01秒。
  补充普通空查询兼容断言后同113项复验通过，1.72秒。
- 两个skill基础校验、改动的collected模块与对应测试Ruff、diff检查通过。
- 将整CLI加入Ruff时仍有既有TRY004（server JSON类型检查）；HEAD同段已核实存在，
  本轮未改该无关逻辑，不把定向Ruff通过冒称CLI全文件无问题。
- 定向检查不代表完整unit/contract回归、宿主行为或安装态；新增outcome与host安全案例
  继续pending。现用0.46.1没有这个选项，源码变更尚未发布安装，也未用源码冒充产品
  在test Vault进行业务验收。

## 还没有解决的真实链路

真实毕设仍缺management声明与本地Run档案。随后已在源码补齐adopt-role的声明接入
预览/apply及旧父子到接收的合成组合，见project-role-adoption-test-results.md；未安装，
不是完整布局/规则/Git策略迁移。旧nonempty generic项目仍不能靠新空根initializer转角色。
远端原始记录格式、本次应收清单和安全传输尚未核对；不能从报告中的路径/数值补造
原始配方或接收回执。服务器只读核对许可仍未收到，无连接或下载。

本清单检查只验证已明确列出且已登记child的本地原始档案，不发现远端全集、不保证
未列实验都已登记，也不替代本地指标/代表性图的内容审阅、真实执行或独立备份验证。
这些缺口不能被113项测试关闭，WI-055与G17保持未完成。
