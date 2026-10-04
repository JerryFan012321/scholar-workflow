# 可复现科研项目示例

这是一个小型确定性工作流样例：代码、实验报告与成果可以从明确资料清单集中调用，不需要 Hub。
它不是任何论文的训练实现；模板不包含外部论文或虚构结论。

## 准备、执行与阅读

前置条件：安装 Scholar Workflow 0.32.3 或更新、Python 3.11 或更新、Git 和 POSIX shell（macOS/Linux）。
模板准备器只生成文件和 Git 骨架，不提交、不运行。项目规则占位符仍待确认填写。

先显式提交这个新示例的源码（只限本新目录，不 push）：

```sh
git add .gitignore .agents assets configs env src tests tools AGENTS.md AGENT.md CLAUDE.md README.md README.zh-CN.md project-layout.json project-context.json reproduction-inputs.json
git commit -m "Create reproducible workflow example"
```

然后在项目根执行：

```sh
python3 tools/replay.py
```

预期：一次错误工作目录的真实失败，随后两次成功；数量 **4**、总和 **10**、均值 **2.5**。
成功结果必须与先行固定的 [独立预期](tests/expected.json) 相符，重放字节一致。
失败日志保留；这不是制造成功，也不证明科学论文结论。

- [实验报告](experiments/20261004-0000-sum-example/report.md) 执行后生成，包含实际结果和记录入口。
- [指标成果](experiments/20261004-0000-sum-example/artifacts/metrics.json) 执行并校验后生成。
- `scholar-workflow project overview --project-root .` 显示明确选择的资料；生成前缺失项会诚实显示。

机器输入、实际运行信息、公开 CLI 返回和校验值另存；不塞进人类正文。
`dataset/`、`docs/`、`experiments/` 本地优先，不随默认源码 Git 备份；复制校验不等于独立备份。

## 新目录重建

克隆同一源码到一个新的目录；保持其 project_id，不把复制当新项目。
用已安装 init-project 的 `scripts/init_project.py plan <新目录>`、`apply <新目录>`
补齐不进 Git 的本地优先目录，再进入新目录执行 `python3 tools/replay.py`。
不要复制旧 dataset 或 experiments 来冒充重新执行。结果应相同，实际主机/时间/执行路径可以不同。

已有目录再次执行须选新 Run，例如：

```sh
python3 tools/replay.py --run-id 20261004-0001-sum-replay
```

已有 Run、输入冲突或用户改动会拒绝覆盖并保留原件。中断后检查已有 Attempt，不能把它改称成功。

## 加入研究材料

只将自己明确选择的论文、笔记或 Canvas 加到 `project-context.json`。
外部正文仍归 Zotero/Vault；清单不授权同步、扫描或执行论文代码，未核验链接不标已通过。
人类可读性与操作便利性仍须评鉴，不能用自动校验代替。
