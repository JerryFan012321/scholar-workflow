# 同目录设备号恢复：独立验证结果

对象与影响见 [测试方案](source-rebinding-plan.md)。仅同路径/inode设备号恢复，
既有正文、Canvas结构与来源证据不改，不扩展到目录搬迁或缺失provider初始化。

## 开发态实际结果（2026-10-08）

- 先新增合成契约测试，实际 RED 为新模块/入口缺失导致 collection error；未把未运行当通过。
- 实现后初始受影响组合76 passed；再补10项边界，新恢复测试共26 passed，相关组合86 passed。
- 覆盖零写入、binding-only/幂等、不改变catalog/归属/历史回执；完整分析/资产/导航读集、
  缺失/禁用/只读Source、路径/inode不同、符号链接、目录替换、检查期间改动、摘要过期、
  prepared/provider-rebound中断恢复与journal篡改。原commit/export安全检查保持。
- Ruff首次指出新文件两处import排列，机械格式修正后通过；git diff --check通过。
- 完整 `tests/unit tests/contract`：1855 passed，11条既有PyMuPDF/SWIG与多线程fork弃用警告，
  89.85秒，无失败。输入仅隔离fixture，没有真实业务写入。

## 安装态独立验收

尚未发布安装0.41.4，不以开发态测试替代本机安装态。
正常提交、runtime-only release与安装后，再仅使用已获批test V-JEPA2 Source：
零写入预览冻结完整文件、复核摘要，合法恢复binding，获取fresh CAS用于同一已审IR。
图片人工评鉴已有明确通过，不重新分析、裁剪或评鉴同一输入。
正式成对提交/provider登记及一次带图新根复现仍待执行，不冒称G17完成或verified backup。
