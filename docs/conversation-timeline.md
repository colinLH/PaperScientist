# 对话时间线、文件预览与逐轮变更

对话页由 Python/Gradio 挂载，浏览器用原生 EventSource 接收持久化事件。无需前端构建服务。

## 使用

- 模型的可见进展与正文逐段流式出现；同一段连续的同类工具调用合并在可折叠块中，点击单条可查看结果。
- 原始内部推理字段不进入展示。生成截断后显示重试提示，成功结果替换残片；未通过完整性检查的工具调用不执行。
- 每轮末尾显示主要文件卡片、其他文件引用，以及本轮修改。前三个修改直接展开，剩余修改折叠。
- 文件支持 PDF 分页、图片、Markdown、CSV/TSV 表格、文本/代码预览；DOCX 提取正文、XLSX 预览首张表。其他格式可下载。HTML/SVG 按源码处理，页面不执行文件里的脚本。
- 右侧每个短横线代表一轮任务；点击跳转，鼠标悬停或键盘聚焦显示问题、回答摘要和文件名。
- 中途回答和同一任务的继续执行归入原轮次；完成后发起的新问题建立下一轮。

## 恢复与文件版本

`research.db` 中 `ui_turns/ui_events` 保存事件。浏览器先读取快照和游标，再通过 SSE 续接；重连使用 `Last-Event-ID` 补发。最终回复/工具返回的展示事件与原始消息、节点收据在同一事务中提交。

`file_turns` 保存修改前后的哈希，原始字节保存在数据根目录的 `file-versions/<session_id>/`，与代理工作区隔离。保存、暂停、完成、出错与停止都会结算变更；恢复执行延用本轮基线。文件快照结束后才显示任务完成。

撤销前校验所有选中文件仍等于本轮修改后版本；存在后续修改时拒绝覆盖。撤销支持单文件或整轮。新增文件被移除前，其修改后快照仍被保存。操作日志支持重启后识别已经恢复的文件，不自动覆盖后来修改的文件。撤销不会倒退会话记录或研究记忆，并会向后续模型上下文记录文件状态变更。

历史会话可完整恢复文字和工具记录，也可预览已登记产物；没有预先记录的文件基线不能追溯撤销。单文件撤销快照上限 20 MB，缓存、运行日志、数据库、符号链接等不纳入；界面提示未跟踪数量。预览源文件上限 50 MB，文本/表格有明确的展示上限。备份时应包含数据库、工作区和文件版本目录。

## 接口

- `GET /api/sessions/{sid}/timeline`：轮次快照和事件游标。
- `GET /api/sessions/{sid}/events?after=<cursor>`：SSE，事件名 `timeline`，15 秒心跳。
- `GET /api/sessions/{sid}/tool-detail`：按工具事件或历史消息 ID 读取结果。
- `GET /api/sessions/{sid}/file-preview?path=...&turn=...`：预览描述。
- `GET /api/sessions/{sid}/file-content?path=...&turn=...`：下载；PDF 加 `page=0` 返回渲染页。
- `GET /api/sessions/{sid}/file-diff?path=...&turn=...`：行级差异。
- `POST /api/sessions/{sid}/undo`：`{"turn_id":"...","paths":["notes.txt"]}`；省略 paths 撤销整轮。

运行中、等待回答和归档对话不可撤销。跨会话读取、路径越界和跨站撤销请求被拒绝。

## 验证

运行 `python -m unittest discover -s tests -v`。`test_timeline.py` 覆盖增量在完成前可见、重连游标、截断重试、历史末条消息、工具结果、事务幂等、文件版本预览、撤销冲突/重启核对、Markdown 安全渲染和 PDF 实际渲染。真实 DeepSeek 验收记录位于本地 `.test-output/timeline-live*.json`，网页验收截图位于 `output/timeline-ui/`。
