# 项目资料候选预览：开发与安装结果

本轮在codex/hotfix-project-context发布并正常安装0.40.0。未替换模范项目资料清单，
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

## 正常发布与安装实证

源码52ac73135ca379f776eabd42af7fe78897bb44ec，runtime
aa1861df517e0e22bab2bc01780e327366475aa7。发布脚本在独立干净clone构建242个runtime文件；
限定个人路径/样例身份扫描无命中，开发层未进入发布分支。source hotfix及release均已推送。
pipx固定runtime commit正常安装，direct_url实际commit完全匹配；PATH CLI报0.40.0，
Codex marketplace正常upgrade/add，实际0.40.0缓存中两个plugin manifest一致。
没有手改缓存或临时产品venv；回退为0.39.0 runtime63a29f12ab47616d8cc38abec9d04738241110c0。

## 安装版单对象公开展示

仅在既有示例根新增project-context-candidate.json，明确引用当前登记正文、Canvas、资料笔记
及既有代码/实验/成果。实际公开validate-context退出0、有效8项；overview中文及JSON均退出0，
JSON明确preview:true与候选名，4本地项available/4外部项unverified。未使用私有模型或源码直跑。
“项目资料-0.40.0预览.md”保存实际Markdown输出于项目根，保持本地相对链接有效；test中
“项目资料整合-0.40.0/使用说明.md”提供原生Vault入口、两条重放命令、状态解释与人工评鉴标准。
同目录保存实际机器响应、校验结果、安装身份及前后hash。原生Codex文件打开请求返回queued，
不宣称已经目视显示、点击成功或人工通过。

说明中的4个Vault文件通过实际路径存在性核对；这不证明原生reader点击成功。
本轮结果记录更新后test_evals_schema的10项全部通过（0.02秒），diff空白检查通过。

四个受保护文件前后hash完全一致：旧context863bedba、旧展示314a357b、代码0b2f9724、指标9e0bb106。
本轮没有重跑既有实验、改论文/Canvas/PDF、迁移正式Vault或启动Hub/cmux workspace。

## 未完成

完整回归、正式hotfix提交发布安装、安装版单项目公开candidate展示已完成。
实际资料清单替换仍待覆盖确认，人工评鉴与真实reader/窗口交互保持pending；G17未完成。
已在会话明确要求打开预览检查资料可发现性、对应对象点击与完整摘录语境，不重审认可的Canvas。
用户三个无关规划文件不纳入提交。未合并main；本次结果留档不新增runtime版本。
