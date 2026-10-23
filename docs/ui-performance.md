# Web 性能优化与验证

验证日期：2026-10-23。保留紫青渐变、星空连线、流星、鼠标光晕、点击粒子和输入框光效。

## 改动

- **特效按预算绘制**：背景最多 24 FPS，持续绘制过慢时降至 12 FPS；粒子上限 48，Canvas 上限 120 万像素。星光和鼠标光晕预渲染后复用。滚动期间暂停背景绘制，停止滚动 180 ms 后恢复；隐藏页面、文件预览时暂停，系统减少动态效果模式显示静态背景。
- **降低合成开销**：用半透明渐变保留玻璃质感，移除覆盖滚动内容的实时背景模糊和超大模糊层。发送按钮光晕使用透明度/位移动画；环境动画在滚动期间暂停。
- **增量更新对话**：流式事件只更新受影响的轮次，50 ms 批量刷新，文本节点追加内容。折叠工具组只渲染摘要，展开时才创建工具行，收起后释放。滚动导航用二分查找，只更新变化的标记；关闭文件预览释放弹窗和图片节点，切换会话取消旧请求和订阅。
- **减少服务空转**：SSE 使用事件通知及时唤醒，空闲数据库兜底查询间隔从 0.1 秒改为 2 秒（查询频率下降 95%）。历史工具正文在 SQL 查询中剔除，再反序列化；完整正文仍可按需打开。
- **减小服务内存**：网页入口默认阻止 Transformers 为云端模型适配器导入不需要的 Torch / TensorFlow / Flax 后端。LangChain 工具绑定、DeepSeek API 调用不变，研究 Python 子进程使用独立的环境白名单，仍可加载本地 ML 库。
- **控制无进展调用**：持续执行模式连续两次没有工具调用的回复会暂停，保留现场并给出原因；用户可继续。普通问答模式仍在一次回答后完成。这是防空转保护，不是任务完成判定或意图分类器。

## 本地回放结果

同一浏览器视口、同一份真实历史快照（16 轮、401 条内容项），分别加载修改前后代码。使用相同 8 秒滚动轨迹；随后回放 100 个流式片段。回放页不调用模型、不修改真实会话。

| 指标 | 优化前 | 优化后 |
|---|---:|---:|
| 滚动帧间隔 P95（越低越好） | 75.1 ms | 37.7 ms |
| 8 秒内动画帧数 | 126 | 242 |
| 滚动期间背景 Canvas 重绘 | 126 | 0 |
| Canvas 像素数 | 2,073,600 | 921,600 |
| 页面 DOM 节点 | 4,113 | 2,153 |
| 最后一轮收到 100 个片段时，首轮 DOM 变化数 | 11,868 | 0 |
| 回放最终内容完整 | 是 | 是 |

原始数据：`output/ui-performance/{before,after}-{scroll,stream}.json`。
该回放隔离了前端渲染，不包含整个 Gradio 页面、推理延迟和操作系统负载。帧间隔与机器负载有关，单次结果不代表所有设备达到 60 FPS。Canvas 像素减少约 56%，这是绘制缓冲规模，**不是 GPU 总占用或显存下降百分比**；未测量整机 GPU 使用率。

## 内存与真实服务验证

- 相同 Python 环境、独立进程导入运行时和 DeepSeek 适配器：默认依赖路径约 **812.5 MiB RSS**，关闭不需要的可选 ML 后端约 **121.3 MiB RSS**。
- 重启后的网页服务约 **245.3 MiB RSS**；完成真实 DeepSeek 普通问答后约 **328.2 MiB RSS**。这是服务进程工作集，不包括浏览器和研究子进程，也不构成内存长期上界。
- 真实验证运行 `1cb117cdfe1548ce8012a751fbdd41f9`：一次模型决策、23 个流式片段、一个完整提交，状态 `completed`，网页最终包含“性能回归完成”。证据见 `output/ui-performance/live-validation.json`。
- 网页检查通过：历史恢复、SSE 连接、工具组展开/收起、PDF 预览和关闭、轮次跳转、滚动时暂停特效及随后恢复。重启时旧页曾记录断线错误，恢复后真实调用正常；没有把断线日志当成应用无错误。
- 一次持续执行验证发现模型在无工具约束下重复回复，已手动停止并保留记录；随后增加无进展暂停保护，并用回归测试验证暂停及继续时计数重置。最终普通问答使用非持续模式完成。

## 测试与复现

```powershell
python -m unittest discover -s tests -q
node --test tests/frontend_effects.test.cjs
```

结果：65 项 Python 测试通过，3 项前端测试通过。Python 日志保存在 `.test-output/performance-regression.log`。

回放工具：

```powershell
# 修改前保存一份，在修改后另存一份；共享相同 snapshot.json。
python scripts/build_ui_perf_fixture.py before --session SESSION_ID
python scripts/build_ui_perf_fixture.py after --session SESSION_ID
python -m http.server 8899 --bind 127.0.0.1 --directory output/ui-performance
```

浏览器分别打开 `/before/index.html` 和 `/after/index.html`，先点击“滚动测量 8 秒”，再点击“流式回放”。记录页面 JSON。已有本次基线请勿覆盖；后续比较使用新的 label。`snapshot.json` 包含本地会话内容，仅用于本机验证。

需要在网页服务进程内使用本地 Transformers 模型时，在启动前设置**进程环境变量** `PS_LIGHTWEIGHT_SERVER=false`，或显式设置 `USE_TORCH=1` 等后端选项。既有显式环境变量优先；这些启动选项不从 `.env` 文件读取。直接导入研究库或运行研究子进程不受该入口配置限制。

实现参考：[MDN Canvas 优化说明](https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial/Optimizing_canvas)中的离屏缓存和减少昂贵绘制操作建议。性能数值均来自本机测量。
