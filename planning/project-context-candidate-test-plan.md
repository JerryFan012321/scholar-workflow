# 项目资料候选：独立测试方案

## 当前缺口与范围

安装0.39.0只能对已生效project-context.json提供公开总览；现有候选展示依赖私有模型调用。
给overview和validate-context增加可选--context-file，选择项目根一个JSON候选，沿用既有
有界、拒绝符号链接/并发变更/重复JSON字段的declaration reader，不新增写入接口或权威文件。
候选始终明确标为preview，不能据此称已应用、来源核验或人工通过；默认旧接口输出不变。
文件名遵守已有root JSON declaration规则：小写字母开头，后接小写字母/数字/连字符及.json。
不扩大共享reader规则，不借预览批准替换正式清单。

## 独立合成输入与预期

现有手写project-context fixture复制到pytest隔离目录，另存project-context-candidate.json。
候选标题和选定资料不同于旧清单，用固定输入比较，不从实现推导预期。

- 成功：读取候选及既有project-layout；只检查候选明确引用的本地路径，外部对象仍unverified。
  Markdown明确“候选预览、尚未替换”，JSON提供preview标志和候选文件名；旧清单、候选和其他
  文件前后字节相等；在缺少旧清单时仍能预览匹配layout的候选。
- 失败：身份错配、非法reader URI、缺失/错误JSON/重复字段、超容量、不安全文件名/路径、
  symlink候选/目录均退出2，没有fallback到旧清单或任何写入。
- 未传选项：现有独立EXPECTED-OVERVIEW逐字不变，现有CLI和安全回归继续通过。
- 禁止副作用：mock Scholar config、Zotero、Hub、subprocess、webbrowser；任何触发即失败。

先运行新增CLI反例见缺接口，再做最小实现；通过后跑project-context unit/contract/CLI和eval
schema、Ruff。提交前完整unit/contract回归。普通确定性测试按全局规则执行，真实数据写入另获授权。

## 安装态与可见交付

开发通过后正常hotfix发布安装，才在既有单个模范项目新增明确候选输入并用public CLI呈现。
不重新初始化项目、运行实验、复制论文或改变Canvas。覆盖既有context和项目资料.md仍需独立确认。
当前Mac锁屏且cmux无live socket，GUI/窗口动作不能冒称通过；不重复等待或缓存截图。
测试结果、preview文本和真实回执分别留档，人类清晰度评鉴在会话明确说明。G17保持active。
