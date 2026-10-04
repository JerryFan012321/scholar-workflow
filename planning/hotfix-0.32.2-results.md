# 0.32.2 安装态可见成果

仅修正 explicit expanded 列间距上限 336→340 px，其他结构、内容、框大小和 2:1 门禁不变。范围/独立预期见 `hotfix-0.32.2-test-plan.md`。

## 自动验证

- 修正前合成 9144/9208 输入：2 failed，实际宽 4552，复现 cap 不足。
- 修正后 v5 容量/结构/安全及版本：68 passed（1.28s）。
- 完整 unit/contract：1423 passed，11 warnings（73.82s）。
- 初次 Ruff 3 项只涉新增测试 import/pairwise，测试运行结束后修正；修正后容量/版本 15 passed（0.55s），四文件 Ruff 与 diff 空白通过。未改独立预期或生产行为。

## 安装态待记录

独立 hotfix 发布/正常安装后，对 test Vault V-JEPA 2 使用公开 CLI；36 claims / 68 内容完整五分支。不得把开发测试冒充实际 pair 生成或人工视觉通过。main 未合并；正式 Vault、旧稿、Zotero、服务均不改。
