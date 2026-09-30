# Hub 论文入口与 Codex 任务：A 阶段结果

## 0.30.0 发布前回归（2026-09-30）

用户批准后运行 `.venv/bin/python -m pytest tests/unit tests/contract -q`：
1217 passed，11 warnings，73.84s。警告来自 PyMuPDF/SWIG 及多线程进程 fork 的弃用提示。
diff 空白检查通过；运行文件个人路径及常见 key 前缀扫描无命中（不是完整密钥审计证明）。
此结果不替代实际安装、模型可用性或人工界面评鉴。

## 目录加载最小回归（用户批准后执行）

`tests/unit/test_hub_vault.py`：6 passed，0.10s。新增的不同 ID、同路径拒绝用例
确认无效 artifact 及资源/主题引用被清除，正常项与诊断保留；原有五项回归通过。
仅使用 pytest 临时合成 Vault，没有访问 Zotero、修改实际 Vault 或安装候选。
修复尚未在新安装包中复验；安装态页面与人工评鉴继续待验收。

## 安装态复验（2026-09-30，未通过）

- 分支：`codex/hotfix-hub-paper-tasks`，未提交/合并/发布。
- 独立 wheel 已安装到 site-packages；wheel SHA256：
  `9eb42fe01c180119850db146757cb5b320f78584d767b786f57605b370804895`。
- 安装前端与仓库 hub.js hash 一致；针对正文锚点隐藏和动作标签的 UI 测试 6 项通过。
- 直接安装 CLI 的 open-hub 成功启动隔离服务并打开 cmux 浏览器；页面目录加载失败。
  日志显示 Vault provider 去掉 fixture artifact 后，资源仍引用 `canary-analysis`，
  HubCatalog 报 unknown artifact。GUI 后续动作未执行，B 不标通过。
- 初次 fixture 调用通过 PATH 误选旧 CLI，启动超时；随后终端 typeText 丢失环境变量
  下划线，候选短暂替换默认受管服务。已用原安装 CLI 恢复，原构建为
  `sha256:6708d147c63f280f366a09bf6ae5f661e898975c230ebd1e9033159ee8381399`，
  恢复后端口 55535。没有修改 Zotero/Vault 内容，但旧浏览器 URL 需重新打开。
- 使用固定环境脚本并 exec 安装 CLI 后，隔离目录正常生成 discovery；不再手输环境变量。
- 下一步：使用受管文件的实际身份准备夹具，增加被拒绝 artifact 的诊断复现。
  不批量改 Vault，不重复论文/批注验收。C 真实 Codex 任务仍需单独批准。

日期：2026-09-30。依据：`hub-paper-task-test-plan.md`；用户明确批准“开始测试”。
范围仅为已展示的合成与定向回归。不是整仓库回归、实际模型可用性证明或发布验收。

## 结果

| 项目 | 首轮 | 修正与复跑 | 当前结论 |
|---|---|---|---|
| 六个新增合成测试文件 | 50 passed / 1 failed | UI fixture 的换行转义修正，失败项通过；后续完整 UI 文件 6 passed | 51 项通过 |
| 七个历史链路回归文件 | 158 passed / 4 failed | TaskRecipe/TaskStore/ExecutionTarget JSON schema 补齐新字段；并发 fixture 继承 owner 的实际模型字段 | 162 项通过 |
| 受影响回归复跑 | — | task_runtime + execution_runtime + UI，共 37 passed | 失败项与相邻回归通过 |
| Python 编译 | — | Hub 模块、Local API adapter、CLI compileall | 通过 |
| Git diff 空白检查 | — | git diff --check | 通过 |
| Ruff | — | 现有虚拟环境与 shell 均无 Ruff | 未执行，不标通过 |

213 是两个已批准测试集合的去重总数，不是另跑一次全仓库套件；37 项复跑不重复计数。

## 失败的具体原因

1. UI 合成测试将 Python 的真实换行放入 JavaScript 单引号字符串，Node 报 SyntaxError。
   只修正 harness 中的转义，正文输入、隐藏机器注释和链接断言不变；不是修改产品来迎合测试。
2. 旧 checked-in JSON schema 禁止新 model_profiles、model_profile_id、实际模型/强度和 Source/Field
   字段，代码与契约不同步。已补齐 schema，仍拒绝额外任意字段，保留旧版本兼容。
3. 两进程互斥 fixture 手工构造 continuation run 时漏掉所属新任务的实际模型字段。
   现在从 owner 继承同一组字段；预期仍为恰好一个成功、一个拒绝，没有放宽 store 校验。
   独立的旧持久任务恢复测试也通过，不以新 fixture 替代旧记录兼容验证。

## 环境与影响

原计划 uv 命令先因默认 cache 权限受限、随后因依赖下载网络受限而无法启动测试。
改用仓库已有 `.venv/bin/python -m pytest`，测试集合与输入不变；没有安装新依赖。
Python 3.14.5、pytest 8.3.4；Node DOM fixtures 使用 Node 24.15.0。
回归出现 5 条既有 PyMuPDF/SWIG DeprecationWarning，没有将其视为功能失败或顺手改依赖。

只使用独立临时 fixture 与 fake provider/process。没有启动真实 Codex 任务、操作正式文库、
改写 Vault、停止旧服务、发布或安装。新增测试结果只在开发仓库保存。

## 尚未通过的验收

- B：V-JEPA 2 卡片实际打开 Obsidian 内 ZotFlow Library Reader、指定 cmux workspace 显示原 PDF、
  相关分析/Canvas/笔记逐项打开。模拟 dispatch 成功不算 GUI 通过。
- C：test Vault 的一次真实 Codex 小任务。仍需单独批准；会消耗额度并产生 result.md。
- Ruff：环境没有可执行程序，未运行。
- 发布/安装、正式 Field 迁移：不属于本轮 A 阶段，也未授权执行。

## B 实机部分结果（2026-09-30）

用户已批准 B。使用独立临时状态的开发候选服务，test Vault 只读登记；未替换安装版服务。
仅以 V-JEPA 2（T3RY3HUA / QR4ZU2S9）执行打开动作；分析和 Canvas 归属由验收目录显式指定，
这证明打开链路，不证明正式 Vault 关系已迁移。正式 Zotero provider 使用正常分页与单篇搜索。

| 项目 | 实际可见结果 | 判定 |
|---|---|---|
| Hub → ZotFlow | Obsidian test 窗口显示 2506.09985.pdf；内部 Zotero Reader 显示正确标题、1/48 页 | 通过 |
| Hub → cmux 原 PDF | 当前默认 workspace 新 browser surface 渲染 QR4ZU2S9 原 PDF，正文和图形可见，没有 Zotero 数据库高亮 | 默认位置通过 |
| 相关文件展开 | 显示分析 Markdown、Canvas、Zotero PDF 和 ZotFlow 来源笔记；缺失 Field manifest 有诊断 | 列表链路通过，呈现待修 |
| Hub 分析预览 | 正文和 ZotFlow 页级链接可见，但露出 claim/point 块锚点 | 不通过 |
| 附件动作 | 同一 PDF 行重复出现两个“在 Zotero 打开” | 不通过 |
| 其他 workspace、失效 destination、逐项原生文件打开 | 尚未执行 | 待验收 |

本轮未改写论文、批注或分析文件，未运行 Codex。停止隔离候选，不停止安装版服务。
下一步仅修复已发现的两项呈现缺陷，再复验受影响入口及剩余 B 项；C 仍须单独批准。
