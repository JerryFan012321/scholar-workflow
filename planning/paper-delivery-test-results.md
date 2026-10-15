# 论文入库与索引交付：定向验证

## 范围与结论

2026-10-15，当前 hotfix 开发树修正三项 skill 的条件交接及旧索引缺链接呈现。
入库、已选分类、Knowledge owner、实际阅读列表分别取证；不新增状态库或强制文件，
不扩展只入库请求，不改变 Field 五列规范、论文分析或 Canvas 格式。
51 项定向合成检查及三项 skill 基础校验通过，随后完整 unit/contract 回归 2759 项通过。
安装态、原生阅读和第一阶段整体未据此通过。开发验证没有修改真实 Vault、Zotero、Notion、
服务或已安装插件；用户随后明确批准 0.44.7 提交、发布并正常安装，实际回执另记。

## 先行输入与预期

固定输入在 `tests/unit/test_projection.py`：条目/PDF key 均缺、空字符串、仅条目、仅附件。
缺失单元格必须明确未关联，不能据此推断文库不存在；现有真实形式 URI 保留，输入不变，
不同兼容端口不改变结果。另用一个临时合成索引检查人工段落、原文件更新与重复生成。
普通单元临时目录仅作可丢弃中间物，不是 test Vault 阅读样板。

独立只读 agent 另审阅组合场景：两篇用户已选集合，一篇 created 且含 PDF，一篇 reused
但无可用 arXiv PDF，现有 Field 列表仍标两篇未入库。预期分别保留真实成功/复用身份、
缺 PDF 原因及未执行的列表/Source Note 状态；实际获准更新时只修对应原行及已存在资料。
不能新增重复论文、伪造分析或以委派审阅冒称真实列表已写成。该预期不是自动验收器。

## 执行结果

1. 直接使用开发虚拟环境时缺 pytest，未执行断言，不计作行为失败或红测。
2. 使用现有 uv lock 和临时 pytest 测试依赖运行先行五项：**5 failed**（1.02 秒）。
   四个缺链接组合及一次索引更新均因静默空格而未满足预期。
3. 修正旧投影的两处缺键输出后，执行：

   ```sh
   rtk proxy uv run --frozen --with pytest pytest -q tests/unit/test_projection.py tests/unit/test_novelty_tree.py tests/unit/test_hub_projection.py tests/unit/test_evals_schema.py tests/contract/test_config_cli.py
   ```

   **51 passed**（1.11 秒）。涵盖表格、旧树复用、受管块、CLI 配置路径及 eval JSON 结构。
   不是完整回归，也不是实际 Zotero 交付或 host 行为自动认证。
4. `skill-creator` 的 `quick_validate.py` 对 ingest-resource、sync-projections、
   build-literature-tree 均返回有效；它只证明基础结构，不证明流程可靠或文献科学支持。
5. Ruff 对本轮 Python 实现和测试返回通过，`git diff --check` 通过。
6. 独立 agent 只读审阅新增契约、条件交接、两处实现和eval/test增量，未发现导入范围扩大、
   旧格式替换Field、缺key冒充未入库、成功状态串用或ZotFlow writer越界的问题。
   这是有限源码边界审阅，不是实际外部系统或所有运行路径通过。
7. 发布前完整执行 `rtk proxy uv run --frozen --with pytest pytest -q tests/unit tests/contract`：
   **2759 passed, 11 warnings**（120.32 秒）。警告来自既有 SWIG 类型及多线程进程的 fork 弃用提示；
   没有失败或跳过项，不运行正式业务、真实实验或外部文库写入。
8. 版本升为 0.44.7 后的 15 项元数据定向检查发现模块常量仍为 0.44.6：14 passed、1 failed。
   同步 `src/scholar_workflow/__init__.py` 后重新执行完整回归：**2759 passed, 11 warnings**
   （112.54 秒）。失败记录保留，不豁免版本一致性。

新增 `paper-import-selected-index-closeout` outcome 和
`paper-index-gap-does-not-authorize-reingest` host-layer safety 场景；不伪造 CLI exit code。
前者保持 pending；本次安装态有限样本已执行，但实际交付与宿主自动触发仍待验证。
路由 description 未改，结果边界见下方发布回执，不以模拟输入认证真实Field/文库。

## 保留与待办

既有项目/实验比较格式改动保留；用户已认可的初始化项目典范不重新生成。
论文完整五分支、折叠摘录、直接证据、图片、直角无交叉 Canvas 及领域四入口均不改。
用户已明确授权 0.44.7 正常提交、发布并安装；安装后只在 Git 管理的 test Vault 做受影响单对象验证。
固定身份、回退和安装验收见 [0.44.7-release.md](0.44.7-release.md)。
正式 γ-World 一组的 Zotero 分类仍等待用户选择，不能把建议项当批准。
