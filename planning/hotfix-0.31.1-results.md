# 0.31.1 hotfix 实际结果

日期：2026-10-02。分支：`codex/hotfix-project-context`。用户已批准测试、提交、发布和正常安装。

| 阶段 | 实际结果 | 状态 |
|---|---|---|
| 发布前 unit/contract | 1355 passed，11 条既有依赖/多进程警告，73.00 秒，退出 0 | pass |
| diff 空白检查 | 无发现 | pass |
| runtime 私人路径/明显密钥检查 | 指定 runtime 文件范围无匹配；不声称是穷尽的秘密检测 | pass（本次模式范围） |
| 版本一致性 | 两个 plugin manifest、pyproject、包版本、lock 均 0.31.1 | pass（文件值） |
| hotfix 提交 / release 发布 | 源码 daea99e，runtime adfb0f2；两分支已推送，main 未合并 | pass |
| Codex 插件 / pipx 正常安装 | 均 0.31.1；pipx direct_url 固定到 runtime SHA，实际导入 site-packages；三个检查入口与已提交 runtime 内容一致 | pass |
| test Vault 安装态单对象校验 | 旧 v4 conformance 无 findings，sidecar 正文/受管图/IR 一致，四文件检查前后 hash 不变 | pass（旧格式兼容） |
| 最新五分支 Canvas | 当前 runtime 没有 Experiments role，尚未实现 | not-implemented |
| 人工报告评鉴 | 新目录已保存报告和 JSON；Obsidian 显式 test Vault 打开/读取成功，待用户评鉴 | pending |

实际命令：`rtk proxy uv run --locked pytest tests/unit tests/contract -q`。
输入为当前源码与合成测试，不访问正式业务数据。测试回归通过不证明新版 Canvas 或论文科学内容。
目标新目录为 test Vault 的 `Scholar Workflow 实验/V-JEPA 2/0.31.1-hotfix-验收/`。
实际安装来自 `adfb0f273437a20714b740c56a4ba5d18540fda9`；源码提交为
`daea99ee2ed4e622dfd7beee6fd08b5f804d8b44`。安装采用正常 Codex marketplace upgrade / plugin add；
pipx 原 uv 环境拒绝覆盖且未损坏，正常卸载后重装；HTTPS Git 获取 SSL 断连，改用 SSH 获取同一固定提交成功。
未手改插件缓存，未从开发目录安装，未更改外部应用或服务。原包卸载仅为正常升级，已被新版本替代。

安装态校验从仓库之外以 pipx Python `-I` 执行，直接读取四个旧输入；使用新安装包的
AnalysisDocument/AnalysisBaseline/validate_bundle 和受管图 hash，无写操作。22 claims、46 points、
58 nodes、57 edges；25 个不同 ZotFlow URI 仅做字符串统计，不证明本轮 GUI 跳页。
机器诊断初次 URI 计数表达式不正确，纠正后重新只读统计；输入与校验规则未变。

test Vault 新目录仅新增 `验收报告.md` 和 `检查结果.json`。报告按新安装 check-consistency 的
范围/结论、问题/证据/建议、覆盖缺口契约呈现；没有访问 Zotero/Notion、核实科学来源、生成新摘录
或五分支样张。旧 v4 通过不等于新格式通过。当前会话技能目录仍显示旧宿主 catalog，实际检查文案
直接读取 0.31.1 缓存；新会话自动加载需另行核实。任何未执行项都不标成功。
