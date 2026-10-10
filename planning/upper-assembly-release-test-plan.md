# 0.43.0 hotfix发布与安装检查

用户2026-10-10批准提交、发布和正常安装。不合并main、不迁移正式资料、不切换服务。

## 对象、输入与先行预期

- 同一上层组合能力批次，分支codex/hotfix-knowledge-ownership；已固定的合成fixture及
  EXPECTED，不用产品输出改写预期。
- 四版本面与lock中本包版本一致0.43.0，依赖锁不漂移。
- 现有unit/contract全通过；有限改动Python Ruff、16skill基础校验、diff通过。
- 既有论文五分支模板/renderer保持；开发解析树候选不进入runtime。
- runtime只来自make-release.sh既有allowlist，无开发文档、测试、个人路径或密钥。
- 固定source的runtime archive、release、wheel/sdist和正常安装的对应文件全字节一致。
- 正常pipx安装固定runtime SHA，Codex经marketplace upgrade/plugin add更新；CLI、两manifest、
  实际模块与缓存同为0.43.0，两个新skill存在。保留0.42.0 runtime回退点。

## 步骤、影响与可见结果

1. 同步版本及说明，运行一次合成完整回归与有限静态检查；只写开发测试临时目录。
2. 明确审查本批文件后提交，干净source在独立dist clone构建release和发行包，复核边界。
3. 正常fast-forward推送hotfix/release，不force、不合并main；正常安装更新本机CLI/插件。
4. 核验实际安装身份和对应字节，结果记录upper-assembly-release-test-results.md。
5. 新skill安装态验收另用test冻结单项目，不重跑实验、分析或整库业务；执行前说明输入补充、
   新独立输出目录及预期。原生点击/美观仍待人工明确确认。

测试不访问Zotero、不写真实Vault/项目/provider、不启动Hub或终端worker；安装只更新明确
授权的Scholar Workflow。失败保留回执，不能以源码直跑或手改cache冒充正常安装。
