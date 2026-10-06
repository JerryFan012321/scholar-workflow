# Canvas 重复来源链接：独立验证

## 对象与输入

仅修复 v5 同一论点有多个独立摘录时，Canvas 重复显示相同打开目标的问题。
合成输入复用 analysis_v5_toy.json，选一个方法点，为同页提供两个完整、独立句子；
另测不同页、不同原生批注目标及中文/英文、Zotero/ZotFlow 两种阅读投影。
不使用正式文库写入、不扫描整库、不重新分析或重排真实论文。

## 兼容决策与修改范围

直接改变默认渲染会令已保存的 baseline 无法按旧 IR 重现，不能这么做。
新增显式 v5 profile.canvas_unique_sources=true：只合并完全相同的 Canvas
展示链接，原始 source spans、身份、hash、正文摘录和各自源链接均保留。
省略或 false 保持原投影和序列化。focused 更新保留该选项，改选项需显式
whole 格式更新；此更新不是重新分析、迁移或改变阅读器。

## 操作与预期结果

1. 先写合成测试，确认旧实现拒绝新选项，保存失败结果；不把失败当已实现。
2. 最小修改 model/schema、Canvas 投影及 focused 合并，并写明可用版本。
3. 同页两段摘录在 Markdown 各自可见，Canvas 只出现一次同目标链接；
   不同页/原生批注的不同目标全部保留。默认旧包、完整 baseline 和 no-op 更新不变。
4. 显式 whole 启用选项可成对更新；所有节点身份、几何、样式和边保持。
   focused 改选项失败，focused 保留选项成功；v4/legacy 不接受启用。
5. 运行受影响的 unit/contract，随后提交前运行完整 tests/unit tests/contract；
   内容与范围没有真实业务动作，测试不代替科学来源或人工图形验收。

## 安装与真实对象边界

目标 hotfix 0.41.2，按正常 runtime-only 发布和安装后才做实机更新验证；
回退为已保留 0.41.1 runtime。版本、source/runtime SHA、CLI/cache 身份单独记录。
仅用原 test V-JEPA 2，显式 whole 采用新呈现选项并修目标点完整摘录，所有其他论点、
证据和布局保持；允许删除原包已有两个重复页链接，不删除任何独立来源或摘录。
先 stage 与独立比较，满足当前 CAS/归属才 commit/apply，冲突拒绝覆盖。
图片候选、正式 Vault、Zotero、项目入口与实验不变；不合并 main。
图片美观、裁剪充分性和项目覆盖权限仍分别待人工确认。

## 可见产物

开发测试结果留在本文，真实单对象输入/回执/比较放 test 原来源审阅目录。
向人交付的是完整句正文、未重排的可编辑树及真实状态，不是新控制面或推理流程。

## 开发结果（2026-10-06）

- 旧实现单项红测如预期拒绝未知profile字段，1 failed；未把它记作已实现。
- 首次后改动测试未显式指向受管worktree而读到旧editable安装：9 failed/1 passed，
  属于测试路由错误；后来4个失败是fixture物理页/Markdown转义的断言错误，已修正。
  实际代码测试指定worktree/src，不冒充已安装产品。
- 最终同目标/独立摘录/不同页/批注/默认兼容/whole/focused/v4及schema：16 passed。
- 完整tests/unit tests/contract：1773 passed，11条既有SWIG与多线程fork弃用警告，
  88.59秒；没有真实文库写入、整库分析、实验重跑或服务切换。
- skill quick_validate和diff检查通过。routing触发词未改；现有摘录真实来源、CAS、
  清理与只读检查安全case保持；outcome新增同目标投影，人工/安装单对象项仍pending。
- 上述为开发证据；正常发布安装、单篇stage独立比较/commit/apply与可见结果尚待。

后续已正常发布安装0.41.2并完成同篇公开stage/commit/apply，独立比较通过，全部几何/边
保持。当前13文件复现输入仅三受管文件变化；GUI因当前Mac锁屏未显示，旧截图排除，
人工及项目权限仍pending。实际结果见canvas-unique-sources-results.md，旧待执行文字为
开发冻结时的历史状态，不覆盖此结果；不重做仍有效的恢复或实验。
