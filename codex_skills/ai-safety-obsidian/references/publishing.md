# 可选：同步使用者自己的私有网站

本地归档与图谱无需 Sites。只有使用者明确要求网站时才启用此扩展，使用当前可用的 Sites 插件和其 skill；缺少插件则说明网站未配置，本地流程仍可使用。
不要继承作者项目、账户、网站 URL 或分享权限。用户已指定目标网站时复用该项目。创建新网站仅在该请求已授权时执行，默认私有。

完成当前 Sites skill 的准备后，在使用者 config.json 中设置：

```json
{"site": {"enabled": true, "project_id": "USER_PROJECT_ID", "url": "USER_SITE_URL"}}
```

如 Sites 需要仓库工作区，配置 workspace 必须使引擎生成的 `work/site/dist` 位于当前插件要求的源码工作区内；不得在 credential/source 准备前修改不属于自己的仓库。
沿用当前 Sites skill 获取凭据和提交/打包方式，不在此 skill 固定过时 helper 路径。凭据不输出、不落盘。
静态入口和 graphify.html 来自本次导出；只发布约定的产物，不上传整个 vault、运行配置或其他个人笔记。

恢复 `work/sync/pending-publication.json` 前，核对当前 graph_hash 和同项目的 saved versions/deployments。
每次发布保存可核验的 commit_sha、archive 路径、project_id、graph_hash、version_id、deployment_id。
将已确认的 commit_sha 和 version_id 写入同一 pending 文件，保留 generation 和 graph_hash；不预填猜测值。
保存或部署结果不确定时先按提交和版本查询已有结果；只需部署已有版本时不重复保存，观察超时不等于失败。
只接受原生 `succeeded` 回执，且 project_id、graph_hash、commit_sha、version_id、deployment_id、url 与本次 pending/配置一致：

```text
<PYTHON> <SKILL>/scripts/workflow.py --config <CONFIG> graph mark-published --receipt <VERIFIED_RECEIPT_JSON>
```

该命令校验字段对应关系，真实远端状态仍需通过插件查询，不得手工编造成功回执。
失败保留 pending、历史和上一成功在线版；新 generation 的 pending 会将旧 pending 归档到 publication-history。
本地同步成功与网站发布成功分别报告。未经实际发布测试，不宣称网站链路已端到端验证。
