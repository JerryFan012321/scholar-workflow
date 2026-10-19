# 已有项目角色声明接入：开发结果

日期：2026-10-19。预先输入/预期见project-role-adoption-test-plan.md，全部在pytest
合成目录执行，无真实项目、服务器、Vault或Zotero操作。现用0.46.1未改，源码未发布安装。

## 已有证据

- 先新增parent/child预览和apply四项，因adopt-role命令不存在而全部失败；不是先生成
  成品再按成品写预期。
- 实现后22项通过；故障扩展至28项后全部通过，0.14秒。三个新故障先红测再最小修复：
  发布后验证异常被误记输入错误、同inode暂存内容改变可能被发布、发布后规则改变仍报成功。
  现均保留实际状态并报告未完成/partial，不覆盖或删除未知材料。
- 补一个旧父/旧子接入、双方登记、原Run接收、require-run核对的公开CLI合成路径，
  原UUID/原始文件逐字节保持，五类Attempt与原child commit保留，不执行模型或Git。
- 角色接入、collection、management、CLI兼容、review fixture和eval结构共142项通过，
  1.99秒。新增module及相关测试Ruff、init skill基础与diff检查通过。
- 首轮完整3110项通过、11既有警告，135.32秒。收尾新增权限拒绝用例，先证实它被误报
  为根目录不可用/exit2，再最小改为安全拒绝exit7；29项角色检查及143项相关复验通过，
  1.99秒。最终完整unit/contract为3111 passed、11既有警告，139.53秒。
- 整CLI的既有TRY004未在本轮改动；新module/相关测试Ruff通过，不冒称整文件lint无缺口。
  开发回归不代替正常安装、宿主one-shot或原生/人工评鉴。
- init-project双语说明同步区分源码Git与总项目资料Git，不再泛称所有新项目都忽略docs/
  experiments；已有Git策略仍须独立审议，未改任何真实忽略文件。
- 收尾离线wheel分发预检通过：126个包文件与当前源码逐字节一致，包含role_adoption，
  四个模块从wheel自身加载，adopt-role/collected两项帮助及新选项通过；未夹带开发层
  或当前用户绝对路径。元数据仍0.46.1，这只是未发布源码的结构预检，不是0.47.0
  发布产物、正常安装或安装态验收；实际CLI/cache未改变。

## 实际能力边界

adopt-role只为完整schema2旧项目新增缺失的schema1管理声明；预览绑定所选根及声明/
规则字节、文件身份和模式，apply仅exclusive创建。已有同角色保留全部children，异角色/
child parent/primary或过期预览冲突拒绝，不清空source profile。锁只协调合作写入者，
外部编辑器/同步器仍须停写，不认证跨机器硬事务。

旧AGENTS、Git忽略策略、PROJECT/唯一计划、context、源码/知识和历史档案原样保留；
remaining_review表示本操作没有核对这些事项，不撤销已有效的人工认可。声明成功不等于
完整迁移、原生Git验证、远端部署、双方登记、原始档案接收、科学正确或verified backup。
源数据格式/迁移规则仍需真实证据，不能从报告反抄生成。真实毕设仍未应用此操作。

## 下一步

0.47.0提交/发布/正常安装及现有test续验确认已提出，尚未收到；不会据目标自动推送或
改已安装缓存。具体单对象独立准备见0.47.0-installed-acceptance-plan.md。
在正常版本发布安装授权后，沿用现有test单对象验收，不创建业务副本或用源码代替安装。
真实项目的角色/规则/Git策略接入先出审议预览；服务器只读核对与原始档案回收仍须其
独立许可。未收到前不SSH、不改实际项目，不关闭WI-055或G17。
