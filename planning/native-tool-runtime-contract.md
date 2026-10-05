# 原生打开：运行期说明与独立验收

## 本轮变化

将已实证的cmux打开步骤放入find-resource的既有resource-location reference，
使安装后的skill可按需调用。不改变定位身份、源码接口、权限或任何已认可Canvas。
0.40.2已正常发布安装，发布/安装身份在下方与分离部署JSON记录；开发验证不冒称GUI验收。

## 冻结测试范围与预期

| 输入/对象 | 操作 | 预期 | 影响与可见产物 |
|---|---|---|---|
| 既有合成Local API/CLI fixtures | 执行tests/unit和tests/contract | 原父子关系、locator、远端/缺失文件拒绝及其他公开接口无回归 | 临时fixture，无业务库写入；pytest真实输出 |
| routing/safety/outcomes JSON | eval schema检查并单独审阅新增两项host行为及打开路由 | JSON合法；打开现有论文不入库、不绑定Hub；命令拒绝不绕过权限 | schema结果只证明结构，行为审阅单独记录 |
| find-resource SKILL及reference | skill validator、引用与runtime边界检查 | 原触发描述不变，按需可发现流程，无个人路径或实机ID | 验证输出与git diff |
| 当前安装cmux与Scholar CLI | 只读help核对 | 已存在get --children/附件get、open和明确目的地参数 | 已读取本机help，不启动窗口，不重跑真实单篇 |
| runtime-only发行包及安装缓存 | 正常release脚本/安装完成后比较身份和规则字节 | 源码SHA、runtime SHA、CLI和双manifest版本一致；新规则实际到达安装包 | 不用源码直跑或手改缓存冒充安装 |

本轮没有新增adapter或业务代码，因此不编造新的模拟窗口“通过”记录。此前单篇原生PDF
实际显示及四文件hash保持证据继续有效。新的用户便利性结论必须由用户另行评鉴，不能由
help、文档校验、安装或测试绿灯替代。

## 人工评鉴（仍待确认）

在cmux“Scholar 原生阅读验收”打开已显示的V-JEPA2原PDF，翻页和缩放，判断打开位置及
阅读操作是否顺手。这不是带Zotero数据库批注的PDF，也不是Zotero内嵌阅读器。
论文新摘录、截图阅读体验和项目清单生效属于其他独立待办，本轮不重复执行。

## 实际结果

第一次完整unit/contract回归：1712通过、1失败、11既有warning（85.42秒）。
失败仅为模块版本常量遗漏，已与package/双manifest统一为0.40.2，随后定向复验版本及eval结构。
find-resource quick_validate通过，原触发description未变；本机open/identify/list-workspaces及
安装版get --help已核对。routing新例仍落既有定位/打开分支，安全例是host_llm行为规格，
不附虚假CLI exit code；outcome保持pending。安装前不冒称规则已部署或人类体验已通过。
无业务逻辑或adapter接口改动；Ruff未安装且Python源码仅版本常量一行变，不因此安装新依赖。

版本修正后定向11项（版本契约+eval schema）全部通过，0.06秒；与前述1712通过结果共同
覆盖原1713项，不宣称重新跑了一次完整suite。Skill及diff检查通过；发布/安装待实际回执。

### 正常发布安装回执

- source：7fb712ab795d160900745b89f53f365b68871184（codex/hotfix-project-context）。
- runtime：8704947fbe4d04deacca17ed0bd1be2225e2d31c。独立干净clone使用既有release脚本，
  从权威remote release正常fast-forward推送；242 runtime文件不含开发层，个人路径/样例ID扫描无命中。
- pipx正常固定已推送runtime SHA安装，PATH CLI为0.40.2；direct_url commit_id及requested_revision一致。
- 只刷新jerry-plugins marketplace并通过codex plugin add正常安装0.40.2，不手改缓存。
  双宿主manifest同版本；安装skill/reference SHA256分别95442c3a…、66dd99bd…，与提交字节相同。
- PDF、Markdown、Canvas、sidecar四hash与本轮前现有证据更新记录相同；不重新启动窗口或重跑业务。
- test既有“原生工具验收-0.40.1”保存“运行期规则更新-0.40.2.md”与“部署结果-0.40.2.json”。
  仍待人工便利性确认；新会话加载新版规则，不宣称当前会话已自动重载。
- 回退：runtime21c29a734795071e0cdfb0a57575ccde31984756仍可从Git获取，按正常安装入口固定
  该提交恢复。安装器已清理旧0.40.1缓存目录，不能依赖本机旧缓存回退；不手工创建缓存。
  不自动执行回退、不修改服务或业务库。main未合并，G17仍active。
