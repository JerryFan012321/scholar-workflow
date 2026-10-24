# track-research

持续关注明确选择的研究者博客、公司／实验室研究网页、代码发布和模型列表。
发现动态与正式归档分开；不需要启动 Hub，也不会自动下载权重。

1. 查看已有渠道：`scholar-workflow research sources list`。
2. 登记所选渠道：`scholar-workflow research sources register --spec channel.json`。
   输入格式和不同来源的写法见[使用契约](../../references/research-tracking.md)。
3. 检查一次：`scholar-research check`。首次成功只建立本次可见内容的基线；以后列出新增和内容变化。
   使用 `--channel ID` 可只检查一个渠道；希望首次就列出当前资料时使用 `--initial-mode report`。
4. 查看保留动态：`scholar-workflow research updates`。JSON 中可取得动态 ID，供 `research mark` 标记已读、已选或忽略。

“已选”不是已经入库或验证。需要归档时，再调用正常的资源入库流程。
检查失败不会清空旧记录；内容变化也不意味着模型效果提高。订阅暂停通过当前登记版本
把 `enabled` 改为 `false`，不删除历史。两个命令都由正常安装包提供；源码测试不代替安装态、
原生展示或新对话复现验收。不会自动创建定时任务或修改 Zotero/Vault。
