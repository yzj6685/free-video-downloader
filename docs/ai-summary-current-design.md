# AI 总结功能当前设计

本文档记录当前 AI 总结功能的实现状态，便于后续新对话继续扩展。

## 当前能力

- 解析视频成功后前端会自动触发 AI 分析，后端提取平台字幕并调用 DeepSeek 生成内容摘要。
- AI 分析使用 SSE 流式输出，前端边生成边渲染，减少用户等待焦虑。
- 解析结果采用同屏工作台：左侧展示视频信息、格式选择和下载操作，右侧展示 AI 总结、字幕、思维导图和问答。
- 分析结果包含四个标签页：
  - `总结摘要`：渲染 Markdown，当前主结构为 `视频概述` 与 `内容大纲`。
  - `字幕文本`：展示转录分段，支持复制全文，支持下载 `SRT / VTT / TXT` 字幕文件。
  - `思维导图`：基于 AI 大纲或字幕分组生成 SVG 图片，支持全屏预览和下载高清 PNG。
  - `AI 问答`：基于当前 `analysis_id` 追问视频内容，回答通过 SSE 流式输出并渲染 Markdown。

## 后端接口

- `POST /api/ai/analyze`：非流式分析入口，兼容保留。
- `POST /api/ai/analyze-stream`：当前前端主要使用的流式分析入口。
- `POST /api/ai/chat`：非流式问答入口，兼容保留。
- `POST /api/ai/chat-stream`：当前前端主要使用的流式问答入口。

分析结果仍使用 `AiAnalysisResponse`：

- `summary`：完整 Markdown 内容，前端直接渲染。
- `outline`：从 `内容大纲` 轻量解析出的结构，用于思维导图。
- `key_points`：兼容旧结构，当前通用摘要不强制生成。
- `suggested_questions`：兼容旧结构，当前通用摘要不强制生成；前端有固定兜底问题。
- `transcript_segments`：字幕分段，用于字幕页、字幕下载、问答相关片段和思维导图兜底。

## Markdown 生成约定

后端提示词位于 `api/app/services/ai_analysis_service.py` 的 `_stream_learning_note`。

当前要求：

- 输出中文通用 Markdown 摘要，不固定为学习场景。
- 必须包含二级标题：`## 视频概述`、`## 内容大纲`。
- `视频概述` 用 1 到 2 个短段落说明主要内容。
- `内容大纲` 最多 5 个一级模块，每个模块最多 3 个子项。
- 一级模块建议格式：`1. **功能点**`。
- 子项建议缩进两个空格：`  - **功能名**：解释`。
- 需要更细时使用四个空格三级缩进：`    - 细节`。
- 不输出 JSON。

后端在 `内容大纲 / 章节大纲` 区域做轻量兜底：

- 将 `• / · / ●` 这类列表符号转成标准 Markdown `-`。
- 删除大纲标题后的 `[00:00]`、`[00:00:00]` 时间戳。

## 前端渲染约定

主要逻辑在 `web/src/App.vue`：

- 解析成功后结果区从普通 Hero 卡片切换为工作台布局，工具卡横跨整行。
- 桌面端工作台使用左右并排布局：`xl` 及以上约 `38% / 62%`，`lg` 到 `xl` 约 `42% / 58%`；移动端上下堆叠。
- 左侧视频卡保留封面/预览、标题、平台、作者、时长、格式选择和下载按钮；原大号 `AI 分析` 按钮改为自动总结状态提示。
- 右侧 AI 面板保留“重新分析”按钮；AI 失败只影响右侧面板，不影响左侧下载。
- 前端通过 `analysisRunId` 忽略过期流式事件，避免用户快速解析新链接时旧视频 AI 结果覆盖当前结果。
- `parseMarkdown` 将 Markdown 拆为标题、段落、引用、列表、代码块。
- 有序列表会自动续号，避免 AI 分段输出时多个模块都显示为 `1.`。
- 位于编号模块后的无序列表会被标记为 `nested`，渲染时加缩进和左侧竖线，形成嵌套关系。
- AI 问答回答复用同一套 Markdown 渲染，避免 `**加粗**`、编号列表原样显示。

样式在 `web/src/styles.css`：

- `.markdown-body`：摘要 Markdown 的普通文档排版。
- `.nested-list`：内容大纲子项的嵌套视觉样式。
- `.chat-markdown`：AI 问答的轻量 Markdown 样式。

## 思维导图策略

前端通过 `buildMindMapNodes` 和 `buildMindMapSvg` 生成 SVG：

- 优先使用 `analysis.outline` 作为导图节点。
- 如果 AI 大纲为空，则按字幕分段自动分组生成兜底节点。
- 导图以左右分支树呈现，文字做截断和换行，避免内容挤出画布。
- 全屏预览使用 `object-contain`，避免内部横竖滚动条。
- 下载高清图时将 SVG 绘制到 Canvas，并按 2 倍尺寸导出 PNG。

## 字幕下载策略

字幕下载完全在前端基于 `transcript_segments` 生成：

- `SRT`：使用逗号毫秒时间戳。
- `VTT`：使用点号毫秒时间戳，并带 `WEBVTT` 文件头。
- `TXT`：使用 `[mm:ss] 文本` 格式。

## 抖音文案兜底

抖音公开视频通常没有可提取的平台字幕。当前后端在前端传入 `douyin-resolver-*` 格式，或 URL 明确为抖音链接时，不再先尝试 `yt-dlp` 字幕提取，而是复用 `DouyinFallbackService` 的解析源，提取作品公开 `title/desc` 作为一段 `transcript_segments`，再进入 DeepSeek 摘要流程。

该兜底只基于公开文案和标题，不伪造画面或语音内容；如果解析源没有返回可总结文案，仍返回 422，并提示后续需要音频 ASR 转写。

## 配置和安全

DeepSeek Key 通过环境变量注入：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
```

不要把真实 API Key 写入仓库、文档或前端代码。

可选环境变量：

```powershell
$env:DEEPSEEK_BASE_URL="https://api.deepseek.com"
$env:DEEPSEEK_MODEL="deepseek-v4-pro"
$env:AI_CACHE_TTL_SECONDS="3600"
$env:AI_MAX_TRANSCRIPT_CHARS="24000"
```

## 验证命令

```powershell
cd api
.\.venv\Scripts\python.exe -m pytest
```

```powershell
cd web
pnpm typecheck
pnpm build
```

## 后续扩展建议

- 增加音频 ASR 兜底，解决无平台字幕视频无法分析的问题。
- 将 AI 分析结果持久化，支持历史记录和跨页面恢复。
- 将流式分析接入任务队列，增加失败重试和成本统计。
- 增加用户体系后，对 AI 分析次数、字幕下载和高清导图下载做额度控制。
