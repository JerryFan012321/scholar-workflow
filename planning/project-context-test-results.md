# 项目中心重构测试结果

## 2026-10-02 最新结果

发布与安装已完成：源码 `1e668e5`、runtime-only release `199792d` 均推送；
Codex 缓存 manifest 和正常 pipx CLI 均核对为 0.31.0，CLI 从 site-packages 加载、非 editable。
main 未合并，未启停旧服务或修改真实资料。安装版本核对不是安装态功能/人工验收。

用户明确批准完整合成回归及通过后的 hotfix 提交、发布、正常安装。
`rtk uv run --with pytest pytest tests/unit tests/contract`：**1313 passed / 11 warnings，73.17 秒**。
原来的身份提示失败用例保持原输入/预期，已通过。警告为 PyMuPDF/SWIG 与多线程 fork 弃用提示。
运行包个人路径/明显密钥静态扫描和 diff whitespace 检查无发现。未编译/lint、未做真实业务验收。
源代码门禁通过，不代表人工总览评价、正常安装态功能验收或完整职责解耦通过。
发布/安装已按授权完成；main、真实资料、旧服务没有主动变更。

以下为前一轮测试与修正的历史记录，不能覆盖上述最新结果。

2026-10-01；分支 `codex/hotfix-project-context`；源码 `0.31.0`。
用户的“ok”批准了 `project-context-test-plan.md` 的 A，不包含发布、安装或 main 合并。

## 执行与结果

| 输入/检查 | 预期 | 实际 | 状态 |
|---|---|---|---|
| 新核心/资料/schema/CLI 四份测试 | 独立清单、安全引用、无 Hub/外部执行、同对象兼容、同语种只读输出 | 96 passed，0.56 秒；实际文本与手写预期逐字一致 | pass（源码合成） |
| 相邻十二份回归测试 | initializer、档案、分析模板及旧兼容安全保持 | 188 passed / 1 failed，14.46 秒 | fail；未隐去失败 |
| 同一个合成项目的真实源码 CLI stdout | 中文总览、五项本地资料、外部未核验、缺失仍可见 | 成功输出 `ACTUAL-OVERVIEW.md`，和已通过的 golden 相同 | pass（源码诊断，非安装验收） |
| 人工可读性与便利性 | 用户明确评价此种整合是否有用 | 尚未得到评价 | pending |
| 正常 hotfix 发布、安装态验收、main 合并 | 分别授权且按正常安装入口验证 | 未执行 | pending |

测试首先因 sandbox 无法读 uv 缓存而未启动；获得执行环境权限后正常运行。
uv 更新了本仓库开发 `.venv` 的 editable 包，并将已有 `uv.lock` 的本项目版本
从 0.29.0 对齐到 0.31.0；这不是 pipx/插件产品安装，未更新用户正常安装或 Hub 服务。
未运行编译、lint、完整 unit+contract；未访问/修改正式 Zotero、Vault、Notion、cmux 或 Codex 任务。
旧 HTTP 回归仅使用测试自管的隔离 loopback listener。

## 唯一失败、最小修正与待复测

失败用例：
`tests/contract/test_experiment_lifecycle.py::test_experiment_rejects_noncanonical_project_identity`。
输入仍为原先准备的单个隔离项目，将 UUID 写成 `urn:uuid:<UUID>`。

- 预期：拒绝非法身份，`ExperimentError` 包含既定 `UUIDv4 identity` 提示。
- 实际：正确拒绝，但变成 `project-layout.json does not contain a valid project identity`。
  失败是错误文本兼容性，不是非法身份被接受。
- 最小修正：`project/experiments.py` 单独转换共享 `ProjectLayoutError`，恢复
  `project-layout.json must use schema_version 2 and UUIDv4 identity`；没有改测试或输入。
- 修正后尚未测试。按“代码变化后重新确认”，仅请求下列原失败用例的一次定向复测；
  不重新运行全部 285 项，不重新生成任何真实分析或业务资料：

```text
rtk uv run --with pytest pytest tests/contract/test_experiment_lifecycle.py::test_experiment_rejects_noncanonical_project_identity
```

当前只能称“96 项新增通过，188 项相邻回归通过，1 项修正待复测”，不能称 A 全部通过。

## 可见产物与人工评鉴

实际输出：`tests/fixtures/project-context/ACTUAL-OVERVIEW.md`；手写预期：同目录
`EXPECTED-OVERVIEW.md`。实际产物按根规则被 `.gitignore` 排除，不作为发布内容。
链接以该合成项目根为基准；示例代码不运行，报告不代表真实实验或结果。

请打开实际 Markdown，判断项目目标、各项用途与资料入口是否清楚，缺失/未核验是否容易理解，
这种可选总览是否有实际便利。源码自动通过不代替此评价，也不代替正常安装态验收。
