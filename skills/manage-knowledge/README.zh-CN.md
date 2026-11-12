# manage-knowledge

从 Zotero 的待整理分类接手已选资料，读取元信息、收录说明和人的批注，再按当前任务
调用已有 Skill，获取原文、补全信息、分析或组织完整资产单元。

```text
scholar-research recommendations --profile personal intake target
scholar-research recommendations --profile personal intake entries --limit 50
```

接收分类在推荐设置或 CLI 中配置一次。推荐入库只传元信息、准备好的介绍、链接和人的
意见；PDF、网页快照及知识单元建设由后续管理任务负责。读取队列不等于已完成分析，
也不自动授予删除、覆盖或跨项目读取权限。

操作入口见 [Skill](SKILL.md)，详细约定见[接收契约](../../references/zotero-intake.md)。
