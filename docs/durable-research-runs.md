# 持续科研任务、重启恢复与人工问答

## 数据位置与启动

`Settings.load()` 依次读取本机加密凭据、`paperscientist.local.json` 的非敏感工作区设置、`.env` 和环境变量；后者优先。相对 `PS_DATA_DIR` 始终相对项目根目录解析，避免从不同工作目录启动时切换数据库。

当前本机固定目录为 `.paperscientist-workspace`。旧 `.paperscientist` 和 `.test-output/deepseek-live` 保留，14 条旧 session（含子任务）已合并。数据库备份在 `.test-output/workspace-before-merge.db`。`research.db` 保存会话、消息、项目记忆、侧栏状态、选中的会话和任务记录；`graph.db` 保存 LangGraph 检查点；`workspaces/<session_id>` 保存文件。

仍使用 `python -m uvicorn web.app:app --host 127.0.0.1 --port 8888` 启动。不要改用一个空的 `PS_DATA_DIR` 后误认为历史丢失。备份应同时包含两份 SQLite 数据库和整个 workspaces 目录；服务运行时使用 SQLite backup API，不能只复制 WAL 模式数据库的主文件。

Windows 本地验证凭据由 DPAPI 按当前 Windows 用户加密，位于 `%LOCALAPPDATA%/PaperScientist/credentials.bin`。不会进入会话、运行配置、检查点或代码仓库。环境变量与 `.env` 仍可覆盖。其他操作系统使用环境变量或 `.env`。界面临时 API Key 只驻留内存；跨进程恢复应配置服务端凭据。

## 执行与边界

默认启用“持续执行研究任务”。网页只启动任务并轮询状态；刷新、关闭或切换对话不会取消它。显式停止、归档和删除会停止相关任务。普通单轮 SSE 接口保留兼容行为。

运行状态：queued / running / recovering / waiting_input / paused / error / stopped / completed。模型用 `finish_research` 明确完成，文件必须存在且不能仍有运行中的子任务。耗尽步数预算或连续工具失败属于 paused，可以继续。该机制不会无限重试，服务关闭期间也不会执行；重新启动服务后会恢复未结束任务。

LangGraph 使用 `AsyncSqliteSaver` 和 `durability="sync"`，每个运行 ID 对应一个 thread_id。工具逐个作为节点执行。`run_receipts` 在事务中同时记录节点结果和对话消息，因此检查点重放不会重复写已确认的消息与结果。如果进程在任意外部工具执行期间退出，该调用被标为未确认，模型需要检查产物后决定后续操作；不能对任意外部副作用承诺恰好一次执行。

Windows Python 工具使用 Job Object：停止、超时或服务退出时清理该执行的子进程树。工作区路径限制和移除子进程环境中的 API Key 仍保留；这不是操作系统级文件系统沙箱。

LaTeX 优先使用 PATH 中的 Tectonic，其次使用 `.tools/tectonic/tectonic.exe`。可用 `PS_TECTONIC_BUNDLE` 或安装目录内的 `bundle.url` 指定经过核验的资源包地址，避免默认转发站的 TLS 故障；本机采用官方转发得到的 `data1b.fullyjustified.net/tlextras-2022.0r0.tar`。首次下载资源会较慢，之后复用当前用户的缓存。编译保留日志，每次最多 300 秒；不完整的编译不能标为成功。

## 中途问答

参考 MarsCode `AskUserQuestion.yaml` 的交互设计，模型调用 LangChain 工具 `ask_user_question` 后转入独立 LangGraph 节点：

1. `interrupt()` 保存问题、建议选项、问题 ID 和当前运行 ID。
2. 页面展示问题卡片，允许选择或自由输入；不默认提交任何答案。
3. 后端校验任务状态及问题 ID，拒绝过期和重复答案。
4. `Command(resume=...)` 恢复同一图；回答进入工具结果，所有同组工具结果完成后再写入对应用户消息，保持消息协议有效。

等待状态不需要活跃浏览器连接，重启后仍可回答。恢复节点在 interrupt 前没有副作用。用户明确停止后，可点击继续恢复任务。

## 上下文与证据

原始历史始终追加保存。micro compact 和 sync summary 只改变模型输入投影。长任务缺少新用户轮次时，sync summary 可以在完整工具调用组之间切分，保留最近的调用组和最新用户原文。不会将 AI 工具调用与其 ToolMessage 切开。

脚本运行记录含脚本哈希、输出文件哈希、退出码、耗时和日志。论文仍需通过实验登记、证据审计及人工科学判断；恢复成功不等于结论正确。

工具调用生成被 token 上限截断或包含无效参数时，整条生成先被丢弃，不执行任何工具。持续任务要求模型缩小生成后最多重试两次；仍失败则保存错误状态。`edit_file` 提供唯一精确匹配替换和小块追加，避免反复重写大文件。运行行创建和初始用户消息之间发生退出，也会在恢复时通过幂等 input 回执补齐。

## HTTP 接口

- `POST /api/sessions/{sid}/runs`：message、project_id、model、allow_execution、continuous、max_steps。
- `GET /api/runs/{rid}`：状态、进度、待答问题、完成产物和错误。
- `POST /api/runs/{rid}/answer`：question_id、answer。
- `POST /api/runs/{rid}/continue`：可选 message；追加指令在当前工具组结束后注入。
- `POST /api/runs/{rid}/stop`：停止，保留历史和检查点。

会话快照包含最新运行状态。界面刷新时恢复上次选中的有效会话；链接里的 session 优先。

## 已有验证

`tests/test_durable_runs.py` 覆盖：中断后跨服务实例恢复、工具消息配对、失效回答、后台任务不随浏览器旧流取消、预算后续跑、长单轮上下文压缩、未确认副作用不自动重放、补充指令的消息顺序，以及删除后清理运行/检查点。

真实 DeepSeek 页面测试记录在 `.test-output/interrupt-live-report.json`：写 before.txt → interrupt → 重启测试服务 → 页面选择 beta → 自动续跑 → 写并回读 after.txt → 完成。此记录是功能验证，不是科研任务成功率。
