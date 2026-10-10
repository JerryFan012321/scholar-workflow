# 0.43.0 hotfix发布与安装结果

2026-10-10，用户明确批准；先行计划为upper-assembly-release-test-plan.md。

## 发布前实际检查

| 检查 | 实际结果 |
| --- | --- |
| 完整unit/contract合成回归 | 2486 passed，107.38秒，11条既有SWIG/fork弃用警告；无失败或跳过 |
| 改动Python Ruff | 全通过；不扩大修复历史lint债 |
| 16个runtime skill基础校验 | 全通过；不冒称实际宿主路由/人工评鉴 |
| 四版本与lock本包 | 全为0.43.0；uv.lock仅本包版本一行变化，24依赖离线检查通过 |
| 开发公开CLI | --version为0.43.0，knowledge list帮助含新选项 |
| runtime边界独立检查 | 262文件；无开发层、symlink/缓存/.review或高置信度私人路径/密钥 |
| 原论文呈现契约 | 原模板、analysis SKILL及renderer无diff；新外框候选不进runtime |
| diff | 通过 |

只用了开发合成fixture和临时目录，没有Vault/Zotero/业务实验或服务写入。
README六处临时尾注随后统一为0.43.0说明，不改功能代码或先行预期。

## 发行与安装

尚在准备。确定source/runtime、发行包及正常安装实际身份须在执行后填写，不提前记成功。
回退点为0.42.0 runtime 67a221680b92822558502f36924b2e862f1ae8d5。
人工评鉴、默认解析树采用、main合并、正式迁移与完整G17分别未完成。
