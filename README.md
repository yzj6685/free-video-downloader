# 万能视频下载器

一个面向本地演示的万能视频下载网站 MVP：复制视频链接，解析视频信息，选择格式并下载到本地。首版聚焦单链接下载和高转化会员入口，同时为批量下载、视频总结、字幕翻译、真实付费能力预留接口与文档。

## 技术栈

- 前端：Vue 3 + Vite + TypeScript + Tailwind CSS
- 后端：Python + FastAPI
- 下载能力：yt-dlp
- 首版数据：无数据库，静态套餐与无状态接口

## 项目结构

```text
.
├── api/                         # FastAPI 后端
│   ├── app/
│   │   ├── main.py              # API 入口
│   │   ├── models.py            # 请求/响应模型
│   │   ├── routers/             # API 路由
│   │   └── services/            # yt-dlp、套餐、能力封装
│   ├── requirements.txt
│   └── tests/
├── docs/
│   ├── requirements-analysis.md # 需求分析沉淀
│   └── solution-design.md       # 方案设计沉淀
└── web/                         # Vue 前端
```

## 本地启动

### 1. 后端

```powershell
cd api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

后端依赖 `yt-dlp`。`requirements.txt` 已包含 Python 包版本；如果想使用系统级命令，也可以额外安装：

```powershell
pip install -U yt-dlp
```

部分高清格式合并需要 `ffmpeg`。未安装时基础解析和部分下载仍可用，但合并音视频的格式可能不可用。

### 2. 前端

```powershell
cd web
npm install
npm run dev
```

默认前端会代理 `/api` 到 `http://127.0.0.1:8001`。如果你希望使用 `8000`，可通过 `VITE_API_PROXY_TARGET` 覆盖。

如果本机 `5173` 已被占用，可以改用：

```powershell
cd api
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

cd ..\web
$env:VITE_API_PROXY_TARGET="http://127.0.0.1:8001"
npm run dev:local
```

## 关键接口

- `GET /api/health`：检查 API、yt-dlp、ffmpeg 状态
- `POST /api/probe`：解析单个视频链接
- `POST /api/download`：下载，优先返回直链，失败时中转
- `GET /api/capabilities`：返回首版能力说明
- `POST /api/ai/summary`：视频总结预留接口
- `POST /api/ai/translate-subtitles`：字幕翻译预留接口
- `GET /api/billing/plans`：返回静态会员套餐

## 抖音、B站等平台 Cookie 说明

部分平台会对网页端解析做访客校验。典型表现：

- 抖音短链返回 `Fresh cookies are needed`
- B站返回 `HTTP Error 412: Precondition Failed`

这不是输入框或前端问题，而是平台要求请求携带新鲜的游客 Cookie 或用户主动提供的 Cookie。下载解析链路默认优先使用公开页面、平台公开接口和后端兜底解析；需要解析必须登录态的内容时，仍建议由用户主动导出 `cookies.txt`，然后配置：

```powershell
$env:YTDLP_COOKIE_FILE="C:\path\to\cookies.txt"
cd api
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

配置成功后，`GET /api/health` 中的 `cookie_file_configured` 会显示为 `true`。请只为你有权访问和平台允许保存的内容提供 Cookie。

## 测试

```powershell
cd api
python -m pytest
```

```powershell
cd web
npm run typecheck
npm run build
```

## 文档

- [需求分析](docs/requirements-analysis.md)
- [方案设计](docs/solution-design.md)

后续 AI 或开发者继续扩展功能前，应先阅读这两份文档，并在功能范围或架构发生变化时同步更新。

## 合规边界

本项目基于 yt-dlp 支持公开或用户有权限访问的视频链接解析与下载。请仅下载你拥有权利或平台允许保存的内容。首版不提供 DRM 绕过、破解、盗取登录态、规避会员墙或下载私密内容的能力。
## 当前解析兜底实现

- B 站：当 `yt-dlp` 触发 412 或游客校验时，后端会尝试读取公开页面中的 `window.__INITIAL_STATE__`，再调用 B 站 HTML5 播放地址接口获取可下载的 mp4，并通过 `/api/download/file` 走后端中转下载。
- 抖音：当 `yt-dlp` 提示 fresh cookies 时，后端不会读取用户浏览器 Cookie，也不会要求用户手填 Cookie。当前实现会先使用 `DOUYIN_RESOLVER_ENDPOINT` 指定的自建/商业解析源；未配置时，尝试默认公开解析源 `https://api.mmp.cc/api/Jiexi`，支持返回 `video.cdn_url` 或 `video.video_url` 后生成直链下载。
- 抖音图集：如果解析源识别为图集或非视频内容，首版会返回明确提示，避免误判为视频解析失败。
- 生产建议：公开解析源稳定性不可控，正式上线建议配置 `DOUYIN_RESOLVER_ENDPOINT` 接入自建签名解析服务或商业 API。该接口可配置多个地址，用英文逗号分隔。

端到端烟测：

```powershell
cd C:\code\ai-code\free-video-downloader
& 'C:\Users\yzj\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' web\scripts\e2e-smoke.mjs
```

该脚本会通过前端同源 `/api` 路径验证 B 站解析/中转下载，以及抖音解析/直链采样下载。可以通过 `E2E_DOUYIN_URL` 替换抖音测试链接。

## 当前交互修复记录

- 视频封面不再由浏览器直接访问平台图片地址，而是统一走 `/api/media/thumbnail`。后端会根据原视频链接或图片域名补充合适的 `Referer`，解决 B 站、抖音等平台图片防盗链导致的封面裂图问题。
- 下载按钮不再使用 `window.open` 打开新标签页。前端会创建临时 `<a download>` 触发下载；B 站和抖音兜底链路都会返回同源 `/api/download/file` 地址，因此不会跳到 `about:blank` 或外部空白页。
- `web/scripts/e2e-smoke.mjs` 已覆盖 B 站封面代理、B 站同源下载代理、抖音同源下载代理。

## 抖音解析体验修复记录

- 抖音解析源如果不返回封面图，前端会使用 `/api/media/video-preview` 加载视频首帧作为卡片预览，不再只显示播放占位图。
- `/api/media/video-preview` 支持 `Range` 请求，默认只返回小片段，避免为了卡片预览拉完整视频。
- 抖音格式列表不再固定为一个选项。后端会从解析源返回的 `video.cdn_url`、`video.video_url` 等字段生成多个可选格式。
- 抖音格式会通过 HEAD 请求探测 `Content-Length`，前端可以显示真实大小，例如 `44.2 MB`，不再显示“大小未知”。

## FFmpeg 本地依赖

项目已支持自动使用项目内置 FFmpeg：`tools/ffmpeg/bin/ffmpeg.exe` 和 `tools/ffmpeg/bin/ffprobe.exe`。后端启动时会优先读取环境变量 `FFMPEG_LOCATION`，未配置时自动查找项目内置路径。

这解决了健康检查里 `ffmpeg_available=false` 的问题，也让 `yt-dlp` 在需要音视频合并、转封装或探测媒体信息时有可用的 FFmpeg 工具链。

可手动验证：

```powershell
.\tools\ffmpeg\bin\ffmpeg.exe -version
.\tools\ffmpeg\bin\ffprobe.exe -version
Invoke-RestMethod http://127.0.0.1:8001/api/health
```

## SiliconFlow ASR

抖音等平台没有公开视频字幕时，后端可以用 SiliconFlow ASR 从视频音频生成真实转写，再交给 AI 总结。不要把真实 API Key 写入仓库，启动后端前用环境变量注入：

```powershell
$env:SILICONFLOW_API_KEY="你的 SiliconFlow API Key"
$env:ASR_PROVIDER="siliconflow"
$env:SILICONFLOW_ASR_MODEL="FunAudioLLM/SenseVoiceSmall"
$env:ASR_MAX_SECONDS="900"
```

未配置 `SILICONFLOW_API_KEY` 时，抖音总结会退回公开视频标题/文案兜底；配置后，抖音 `douyin-resolver-*` 格式会优先走 ffmpeg 抽音频和 SiliconFlow 转写。

抖音 AI 总结失败的完整修复沉淀见：[docs/douyin-ai-summary-fix.md](docs/douyin-ai-summary-fix.md)。
