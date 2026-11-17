# 推荐反馈回原聊天与两文件任务目录：实施结果

日期：2026-11-16。独立分支 `codex/hotfix-recommendation-queue`，基线 `3a66365`，
0.57.0开发候选。本记录区分源码实现、开发回归、发布安装和实际聊天验收。
已确认方向见[框架第4节](../specs/report-learning-intake-plan.md)。

## 实施范围

项目内每个推荐任务只持有 `.agents/context/recommendations/<producer_id>/context.md`
与 `recommended.md`，没有 `tasks/` 中间层。前者维护当前要求和消化后的反馈，后者由任务
agent在实际推荐后记录日期、标题、原文链接及必要简述；反馈处理不虚增已推荐记录。
首次绑定安全创建缺失文件，已有人工内容保持原字节，不要求组件启用或改写AGENTS。

推荐提交保留原条目框架；producer可附 `feedback_target`，将明确项目根和原本地Codex聊天
绑定到中央任务身份。新提交和显式 `tasks bind` 复用同一绑定逻辑；重新绑定使用当前revision，
旧反馈保留自己的路由快照，不跟随新聊天静默改投。

人的选择、评价、撤回和已处理条目的标签修改先保存中心事务，再由确定性代码打包消息，
经参数数组调用 `codex queue`。消息保留指定中文前缀、用户所见资源版本、该任务自己的原始
推荐记录、人类反馈原文、标签、事件身份、任务文件及原数据池定位。同条目由多个任务推荐时
分别反馈给已绑定来源；不任取首个推荐者，不混入其他任务的推荐说明。

中心保存pending/queued/uncertain/completed、真实开始处理时间、尝试次数和完成摘要／context摘要值。
队列回执不冒充上下文已修改；超时、进程中断和未知回执不盲目重投。明确失败可重试，
uncertain须核实未入队后以精确事件、任务和尝试次数执行 `feedback retry`，再 `feedback sync`。
retry保留复核事实，已开始处理的消息不能以“未入队”重试。接收者先提交start，再更新context，
读回当前摘要值并complete；这些回执不推进中心curator的独立消费。

旧 `projects enable`、`tasks register/save-context`、项目反馈JSONL投影、消费checkpoint和
组件／额外入口生成链路已从新实现移除。schema-1登记与中央原始记录保留可查，实际旧项目
资料未经本轮迁移或删除。共享偏好、中央daily inbox、curator批次、来源管理及审阅入库保留。

## 测试计划与输入

| 对象与输入 | 操作及通过标准 | 影响与可见结果 |
|---|---|---|
| 临时项目、人工Markdown、临时中央池 | 绑定／重复绑定／revision改绑／经原提交入口绑定；只出现两个任务文件，原内容不变 | 仅pytest临时目录；返回文件定位、任务revision |
| 合成推荐、合并的多producer、人类意见与标签 | 保存反馈、冻结资源和归属、打包并调用注入runner；消息前缀／原话／当前标签准确，每个来源只收到自己的原始推荐 | 不运行真实Codex，不操作正式推荐数据 |
| 模拟queue接受、非零退出、缺失程序、超时、中断、错误线程、超限 | 核有效目标线程回执，重复sync不重投已接受或不确定消息；超限保留全文及可见错误 | 中央投递记录；无截断、无隐式改投 |
| queued/uncertain事件、任务文件摘要、显式start/complete/retry | 回执幂等、错误任务／旧route／旧attempts／错误digest拒绝；start和completion独立于curator | 仅中央回执，不生成项目状态文件 |
| symlink、hardlink、祖先目录替换、legacy登记、test profile | 拒绝不安全路径及旧布局静默采用；test不能启动真实queue | 人工资料保持，旧事实可查 |
| 中央批次和投影并发交错 | consume与flush之间变化不被旧投影确认覆盖；再次sync清理已消费inbox，历史保留 | 仅临时中央JSONL和数据库 |
| 全部unit/contract与推荐相关回归 | 保留原有来源、排序、评价、审阅、Zotero模拟入库及其他模块合同 | pytest结果；浏览器环境跳过项单列 |

开发使用已有Python测试解释器和 `PYTHONPATH=src`；这是开发环境，不是产品安装。
没有向真实聊天发消息、修改宿主定时任务、触发正式推荐、连接Zotero写库或修改正式Vault。

## 已观测结果

- 2026-11-17提交前对最终源码重跑全部unit/contract：4713 passed、22 skipped、11 warnings，
  232.77秒。覆盖下述全部收尾接口与修复，没有失败。
- 第一轮定向接口回归：94 passed。
- 第一轮全部unit/contract：4690 passed、22 skipped，238.88秒。跳过项为环境依赖的浏览器验收；
  出现第三方SWIG与多线程fork的弃用提示，没有测试失败。
- 收尾增加原池定位、显式恢复、开始回执、中央消费／投影交错、已开始后的异常返回和后台
  Codex路径查找后，最终推荐相关回归：668 passed，24.27秒。包含完整推荐unit/contract、
  新反馈测试、eval结构、项目初始化、Zotero模拟分页及版本检查。
- 最终反馈专属39项加CLI恢复6项均在上述668项中，不重复累计成另一批测试。
- 两个修改的Skill通过quick_validate；四处版本均为0.57.0；7个Python文件可解析，4个JSON文件
  可读取，13份Markdown中的92个本地链接可达；最终差异检查通过。
- 本地wheel打包通过，178个文件；8份改动的Python/schema文件逐字节与当前源码一致。
  wheel SHA-256：`d3b1666dd682c7bdff140ca6769e2360fb3448e7f99d588d578c631f361c33eb`。
  这是开发打包检查，未生成正式runtime-only发布或执行产品安装。

可见开发产物为本工作树的 `build/validation/recommendation-queue.xml`、
`build/validation/recommendation-queue-wheel.json` 与 `build/artifacts/scholar_workflow-0.57.0-py3-none-any.whl`。
它们在忽略的build目录，不进入运行分发或个人资料库。

以上第一轮全量结果发生在最后收尾接口加入前；后续结果必须独立列明，不将它当作最终新增接口的覆盖。

## 待安装态及人工验收

本候选未正式发布、安装或切换个人推荐服务，未合并main。此前0.159.3的原聊天queue标记实验
只证明已加载的活动聊天可在原轮结束后处理下一条消息，不能代替本候选的反馈闭环验收。
未加载聊天、App关闭、电脑休眠或重启后的投递恢复也没有得到本轮验证。

安装态应通过正常安装入口部署确定提交的候选，再用一个明确授权的合成条目、专用项目与原聊天：
在推荐条目保存一条意见，观察同聊天出现指定前缀消息、start回执、实际context修改和complete回执；
确认不新增推荐，不改定时任务，recommended文件不因反馈而增加条目，中心curator仍有独立待消费记录。
用户需在聊天阅读反馈结果、打开两文件比较实际表述，判断意见吸收是否准确；未明确确认前为待人工评鉴。
本记录不将模板或指令检查等同于LLM已实际完成上述操作。
