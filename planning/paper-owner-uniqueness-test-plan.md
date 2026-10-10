# 登记前跨 Source 论文归属检查

2026-10-09，独立开发切片。只补已有“一个正式单元一个主归属”的登记安全行为，
不定稿PROJECT/literature布局，不实现Field引用写入，不改论文分析格式。

## 独立输入与预期

先于产品改动准备`tests/fixtures/paper-owner-uniqueness/EXPECTED.md`和合成用例。
两个显式注册的临时Source；A已有一个正式论文声明，B是本次目标；假Local API提供
固定标题、Zotero文库123、论文ABCD2345、附件EFGH2345和小型合成PDF字节。
不请求真实Local API、不读取Vault、不联网。

| 情况 | 预期 |
|---|---|
| A已持有相同Zotero文库/论文身份，B申请新owner | plan拒绝重复；无内容写入 |
| A的旧资源ID不能证明文库，item key相同 | 报无法核验，不冒充重复或放行新owner |
| A的规范ID与Zotero item声明矛盾 | 报无法核验，不选择任意一方 |
| key相同但明确不同文库123/456 | 可以预览，不按key单独判为重复 |
| 同一个Source已持有123，同key的新文库456 | 同样允许预览；不能只修跨Source而保留本地误判 |
| A provider缺失/损坏/符号链接/FIFO，或Source禁用/根失效 | 拒绝宣称已核对全体；B不写入，不扫描补全 |
| B计划后A声明变化，即使不是新增重复项 | 旧digest失效；B无正文/导航/provider内容写入 |
| B中断后A声明变化 | 拒绝恢复；保留已写片段和journal，不覆盖人/外部变化 |
| B发布一个成员后A声明变化 | 下一成员前停止；不继续导航/provider发布，不假报完成 |
| A不变，B恢复同一中断事务 | 正常完成，固定owner路径与文库456身份正确 |
| B的半成品正文被人工改写 | 恢复拒绝，人工内容及其他成员保持 |

已注册集合与声明读取集必须绑定digest，并在apply/recovery中复核；未来实现不能只在
plan瞬时查重。缺失声明不是“已证明空库”。新空Source初始化语义与跨library旧ID的
证明不足需明确保留，不能为了通过测试发明关联或自动迁移。

## 本轮执行范围

先运行新增独立合成用例观察现有实现，预期重复/未知/漂移用例RED，不宣称产品已修复。
命令：`rtk proxy uv run --offline --with pytest python -m pytest tests/contract/test_paper_owner_uniqueness.py -q --tb=short`。
所有写入仅pytest临时根；现有产品源码、正常安装、真实资料、服务与远程分支不变。
可见产物是手写EXPECTED、具体失败列表及分离结果记录。后续实现后按同一预期复验，
补齐空Source和并发边界及必要登记/归属回归；不能以这组定向测试认证完整阶段。

## 实现后定向边界（先写预期，再修改对应实现）

在同一合成临时根补充：规范ID/kind矛盾、前导零文库身份、committed正常重放与内/外
声明漂移、同字节替换文件、Field修改、Source/provider根替换、registry集合变化及锁顺序。
已存在的原receipt链在内部重复夹具中保留，避免仅因丢receipt拒绝而误称唯一性已覆盖。
仍仅执行本文件与必要登记/归属回归；不写真实资料、不装包、不联网。另独立准备新Source
显式空库存初始化预期，只有全文审阅后才实现其组合事务，不把旧missing provider猜为空。
