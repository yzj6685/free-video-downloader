# 万能视频下载器阶段总结

## 当前状态

项目已经完成本地 MVP 的核心闭环：前端可粘贴单个公开视频链接，后端解析视频信息，前端展示标题、作者、时长、格式、大小、封面或视频预览，并可触发下载。

当前本地服务端口：

- 前端：`http://127.0.0.1:5174`
- 后端：`http://127.0.0.1:8001`

当前健康检查预期：

```json
{
  "status": "ok",
  "yt_dlp_available": true,
  "ffmpeg_available": true
}
```

## 已实现能力

- Vue 3 + Vite + Tailwind CSS 前端首页。
- FastAPI 后端接口。
- `yt-dlp` 通用解析能力。
- B 站公开视频兜底解析与后端中转下载。
- 抖音公开视频兜底解析，不要求用户提供 Cookie。
- 抖音多格式展示：从解析源返回的 `cdn_url`、`video_url` 等字段生成多个格式。
- 抖音格式大小展示：通过 HEAD 探测 `Content-Length`，填充 `filesize`。
- 封面代理：`/api/media/thumbnail` 解决平台图片防盗链。
- 抖音无封面兜底：`/api/media/video-preview` 使用视频首帧预览，并支持 Range 小片段请求。
- 下载交付统一走同源代理优先，前端用 `<a download>` 触发，不再打开 `about:blank` 空白页。
- 静态会员套餐、AI 功能占位接口、能力说明接口。
- 本地 FFmpeg 支持：后端会优先读取 `FFMPEG_LOCATION`，否则自动查找 `tools/ffmpeg/bin`。

## 关键接口

- `GET /api/health`：检查 API、yt-dlp、FFmpeg 状态。
- `POST /api/probe`：解析单个视频链接。
- `POST /api/download`：生成下载交付信息。
- `GET /api/download/file`：后端中转下载文件。
- `GET /api/media/thumbnail`：代理封面图片。
- `GET /api/media/video-preview`：视频预览流，主要用于抖音无封面兜底。
- `GET /api/capabilities`：首版能力说明。
- `GET /api/billing/plans`：静态会员套餐。
- `POST /api/ai/summary`：视频总结占位。
- `POST /api/ai/translate-subtitles`：字幕翻译占位。

## 关键文件

- `api/app/services/ytdlp_service.py`：通用 yt-dlp 封装、FFmpeg 路径注入、下载流、封面代理、预览 Range 流。
- `api/app/services/bilibili_fallback.py`：B 站 HTML5 mp4 兜底解析。
- `api/app/services/douyin_fallback.py`：抖音解析源适配、多格式生成、文件大小探测。
- `api/app/routers/video.py`：视频解析、下载、封面、预览接口。
- `web/src/App.vue`：主页面交互、封面/预览展示、下载触发。
- `web/scripts/e2e-smoke.mjs`：端到端烟测。
- `docs/requirements-analysis.md`：需求分析沉淀。
- `docs/solution-design.md`：方案设计沉淀。

## 测试与验收

常规验证命令：

```powershell
cd C:\code\ai-code\free-video-downloader\api
.\.venv\Scripts\python.exe -m pytest
```

```powershell
cd C:\code\ai-code\free-video-downloader\web
& 'C:\Users\yzj\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' .\node_modules\typescript\bin\tsc --noEmit
& 'C:\Users\yzj\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' .\node_modules\vite\bin\vite.js build
```

端到端烟测：

```powershell
cd C:\code\ai-code\free-video-downloader
& 'C:\Users\yzj\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' web\scripts\e2e-smoke.mjs
```

当前最近一次验证结果：

- 后端测试：`10 passed`
- 前端类型检查：通过
- 前端生产构建：通过
- 端到端烟测：通过
- B 站：解析、封面代理、下载代理通过
- 抖音：解析、多格式、大小、预览、下载代理通过

## FFmpeg 说明

本地已经安装 FFmpeg 到 `tools/ffmpeg/bin`，但 `.exe` 文件不进入 Git，避免仓库体积过大。

新机器恢复 FFmpeg：

```powershell
.\scripts\install-ffmpeg.ps1
```

后端检测顺序：

1. `FFMPEG_LOCATION` 环境变量。
2. 项目内置路径 `tools/ffmpeg/bin`。
3. 系统 PATH 中的 `ffmpeg`。

## 合规边界

项目只面向公开或用户有权访问的视频内容，不实现 DRM 绕过、会员墙绕过、私密内容下载、自动读取用户浏览器 Cookie、公共账号 Cookie 注入等能力。

抖音当前通过服务端解析源实现公开视频解析，不要求用户提供 Cookie。正式上线建议替换为自建签名解析服务或商业 API，并做好可用性、限流、成本和合规控制。

## 下一阶段建议

- 增加用户体系、套餐权限、订单和支付回调。
- 增加数据库，记录下载次数、历史和会员状态。
- 增加批量下载队列。
- 增加真实 AI 能力：优先基于字幕做视频总结和字幕翻译。
- 增加 Docker 部署和后台任务队列。
- 将抖音解析源替换为可控的自建或商业服务。
