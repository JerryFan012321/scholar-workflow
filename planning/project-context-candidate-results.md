# 项目资料候选预览：开发结果

本轮在codex/hotfix-project-context准备0.40.0；实际安装仍0.39.0。未替换模范项目资料清单，
未运行其算术示例或改变论文/Canvas。public候选preview和生效更新严格分开。

## 已实现

overview与validate-context的可选--context-file选择一个项目根JSON声明，复用现有reader，
同项目身份与已有格式规则。默认读取project-context.json、旧JSON/Markdown完全保持。
候选Markdown/validation明确“尚未替换”，JSON加preview:true和context_file；不新增第二事实源
或提交入口。init-project与共享project-context规范指向公开命令，不推广内部思考或固定科研步骤。

## 独立检查与实际结果

范围和手写预期见project-context-candidate-test-plan.md；pytest目录使用合成fixture，无真实写入。

- 实现前19项中7失败/12通过，失败证明公共选项缺失；旧解析器直接拒绝选项形成的12项通过
  不算已覆盖新安全路径。实现后负例确认不是“No such option”，确实到达声明reader。
- 首次实现组合104通过/1失败：英文未应用断言写成“not replaced”，实际正确输出“has not been
  replaced”。修正测试短语匹配，不降低未应用要求；定向最终105 passed，0.28秒。
- 首次Ruff发现新增import排序；系统python运行skill validator缺yaml。排序修正、改用开发
  环境验证；随后Ruff全部通过，skill validator有效，diff空白通过。没有给系统或产品环境安装新依赖。
- 最终完整unit/contract：1695 passed、11既有DeprecationWarnings，85.34秒，无失败。
  两plugin manifest、package/module/lock版本同步0.40.0；代码之外仅后续说明追加，不重复全量业务。

## 实机只读核对与权限边界

model-project-0330当前6项清单仍引用旧0.32.3候选。既有独立8项候选指已登记正文并补Canvas/资料笔记。
当前context保护hash863bedba…；候选11c5f675…；指标9e0bb106…。
installed0.39.0 validate-context有效6项，experiment validate为1Run/3Attempts/1Target/1Artifact；
只是只读现状检查，不代表重新执行或全篇科学支持。知识reader明确定位现有test Vault。
旧清单替换批准已在会话独立请求，未收到前不覆盖context或项目资料.md。

原生cmux0.64.25(106) b685a275c实际安装，应用内CLI可调用；当前PATH命令不可用且ping/list
都报告无live socket。只查原生能力，不启动workspace，不引历史Hub登记或从闭锁截图假称GUI通过。

## 未完成

完整回归已完成；正式hotfix提交发布安装、安装版单项目公开candidate展示尚待完成。
人工评鉴与真实reader/窗口交互保持pending；整个G17没有完成。用户三个无关规划文件不纳入提交。
