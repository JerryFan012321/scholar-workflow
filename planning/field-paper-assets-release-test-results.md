# 0.43.1 附件清单 hotfix：发行与安装结果

2026-10-10，用户明确授权提交、发布和正常安装。先行范围与预期见
field-paper-assets-release-test-plan.md；不合并main、不切换服务、不改论文正文/Canvas。

## 发布前实际证据

| 检查 | 结果 |
| --- | --- |
| 当前功能代码完整unit/contract | 上一轮2525 passed / 11既有warnings，107.65秒；含39资产用例，功能代码未再改 |
| 版本后必要回归 | runtime版本、双manifest、eval schema、附件和论文清单共95 passed，3.00秒 |
| 版本一致 | 两manifest、包版本、模块版本及lock本包均0.43.1，依赖未变 |
| 16个skill基础校验 | 全部通过；未改description/触发方式，不冒称宿主或人工验收 |
| 五个修改Python Ruff | 离线检查全通过 |
| diff | 通过 |
| 独立运行期审查 | 8个相关runtime文件无阻断项；未见开发层/私人路径/密钥泄漏或扫描、内容读取、写入权限扩大 |

本轮不重复全量功能测试或任何业务分析/实验。独立审查不代替测试、安装或GUI。
上一完整回归的红测、边界修正及失败观察保留在field-paper-assets-test-results.md。

## 发行、安装与单对象复验

尚未执行。下次记录须给出固定source/runtime SHA、正常安装身份、runtime/package/cache
字节对应和已登记test单Field复验实际结果；不能以准备完成代替发布安装成功。
0.43.0覆盖失败记录和PROJECT/实验报告人工待评鉴状态保持。
