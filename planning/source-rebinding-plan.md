# 同目录设备号恢复：0.41.4 独立验证方案

## 输入与操作

开发测试使用已有合成单 Source/单论文完整配对 fixture。只把历史 provider 中设备号改为
不同值以模拟本机已观察问题；预期原提交/导出仍拒绝。新公开 rebind-plan 零写入，读取
已登记根和完整明确 inventory；rebind 必须确认该方案精确摘要，不能接收客户端绝对根。

## 预期与拒绝

- 恢复只改 provider 的 vault_binding 与随之派生的 snapshot revision，保留 catalog、归属、
  relations、历史 receipts、全部 Source/Field/资产/正文/Canvas/sidecar 字节。
- 同路径、同 inode 可恢复设备号；不同路径/inode、未知/禁用/只读 Source、symlink、
  缺失或被修改的分析/资产全部拒绝。
- 方案后 registry/provider/manifest/任一明确文件或目录身份变化使摘要失效。
- 在准备后或发布后中断可按相同 journal/digest 恢复；并发修改和篡改 journal 不覆盖。
- CLI 有中英文可读预览及独立 JSON；成功不代表科学支持、原生打开、人工评鉴或 verified backup。

## 验证范围和产物

先新增定向契约测试并实际观察缺少入口失败，再实现；只运行受影响的合成案例及必要回归。
稳定后运行完整 `tests/unit tests/contract`（含 eval schema），不执行真实 Vault 或实验业务。
结果单独记录于本方案旁 results 文档，不能以开发态通过冒充安装态通过。

发布安装正常 0.41.4 后仅当前 test V-JEPA2：公开预览/确认恢复绑定；fresh provider CAS
仅更新已通过的同一 IR 的操作上下文（必要时新 batch，不重新分析），正式 commit/apply。
核对旧节点/边/正文/摘录保持，只有图2/表2和准确反链新增，之后一次明确新根归属复现。
已有原件恢复副本与图片人工通过保留；其他业务集合和源码/实验均不写。
