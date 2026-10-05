# 单篇 Canvas 便携登记测试

对象：一个合成 Source、根 Field、已登记论文与通过 v5 成对提交/provider apply 的三文件。
不使用真实 Zotero、不启动 GUI、不写正式 Vault；保留旧论文框架与几何测试。

1. plan 两次一致且零写入；只选择显式 artifact ID，不按文件名发现归属。
2. register 只新增 artifacts.yml 的所选 Canvas 声明；三文件/provider/Field/registry 字节不变。
3. 重复原确认摘要返回同一结果；模拟清单写后中断，可条件恢复。
4. 旧无关声明和注释保留；同 ID 不同归属/同路径不同 ID、重复键/重复行均拒绝。
5. Canvas/Markdown/sidecar/Field/provider/registry 在预览后变化时拒绝；目录 symlink 与
   发布时目录置换拒绝，不覆盖人工修改，保留恢复 journal。
6. public CLI 预览/确认/错误退出与旧 Canvas manifest reader 兼容验证。

通过标准：确定性断言以上真实行为，不把格式符合视为科学支持、人类审美或跨机 provider 恢复。
可见产物：pytest 结果及后续安装版单篇预览；安装前不将真实 test 清单写入算验收。
提交前另跑完整 tests/unit tests/contract，输入仅既有合成 fixtures，预期无回归；
其临时文件在 pytest 隔离目录，结果写独立开发记录。高推理强度测试与业务写入授权独立处理。
