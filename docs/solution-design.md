# 方案设计文档

## 总体架构

项目采用前后端分离：

- `web/`：Vue 3 + Vite + TypeScript + Tailwind CSS，负责工具首页、解析状态、下载交互、会员转化 UI。
- `api/`：FastAPI，负责视频解析、下载交付、能力说明、AI 占位、套餐数据。
- `docs/`：沉淀需求和方案，作为后续扩展上下文。

首版不使用数据库，不启动任务队列。接口保持无状态，适合本地演示和后续扩展。

## 下载流程

1. 用户在前端粘贴视频链接。
2. 前端调用 `POST /api/probe`。
3. 后端调用 yt-dlp 获取元数据和格式列表。
4. 前端展示视频信息和格式选项。
5. 用户点击下载，前端调用 `POST /api/download`。
6. 后端优先尝试返回直链。
7. 如果直链不可用或客户端不适合直接下载，则使用后端中转流式返回。

部分平台会要求游客 Cookie 或用户 Cookie，例如抖音短链可能返回 `Fresh cookies are needed`，B站可能返回 `HTTP Error 412`。首版采用安全配置方式：后端不自动读取浏览器 Cookie，只支持用户主动配置 `YTDLP_COOKIE_FILE` 指向 cookies.txt。未配置时接口返回 428 和可执行提示。

## 后端模块

- `app/main.py`：注册 FastAPI 应用、CORS、路由。
- `app/models.py`：集中定义请求和响应模型。
- `app/routers/video.py`：健康检查、能力、解析、下载。
- `app/routers/ai.py`：视频总结和字幕翻译占位接口。
- `app/routers/billing.py`：静态会员套餐接口。
- `app/services/ytdlp_service.py`：封装 yt-dlp 调用和错误映射。
- `app/services/billing_service.py`：静态套餐数据。
- `app/services/capabilities_service.py`：首版能力说明。

yt-dlp 调用集中封装，后续扩展队列、会员权限、缓存、日志时不影响路由层。

## API 设计

### `GET /api/health`

返回：

- API 状态。
- yt-dlp 是否可用与版本。
- ffmpeg 是否可用。

### `POST /api/probe`

请求：

```json
{ "url": "https://example.com/video" }
```

返回：

- 视频标题。
- 作者。
- 平台。
- 封面。
- 时长。
- 格式列表。
- 推荐格式。
- 是否可能需要后端中转。

### `POST /api/download`

请求：

```json
{
  "url": "https://example.com/video",
  "format_id": "best",
  "delivery": "auto"
}
```

返回两类结果：

- JSON：直链下载信息。
- 文件流：后端中转下载。

### `POST /api/ai/summary`

首版返回 `coming_soon`，为后续视频总结预留。

### `POST /api/ai/translate-subtitles`

首版返回 `coming_soon`，为后续字幕翻译预留。

### `GET /api/billing/plans`

返回静态会员套餐，用于前端弹窗展示。

## UI 设计方向

参考 `https://ai.codefather.cn/painting` 的内容型工具站风格：

- 顶部导航清晰，但首屏主体必须是工具。
- 大标题 + 输入框形成强操作入口。
- 使用高密度卡片网格展示平台、场景、会员权益、AI 能力。
- 视觉上要比普通后台组件库更有消费吸引力。
- 移动端必须可用，避免输入框、按钮、弹窗、结果卡片横向溢出。

首版页面模块：

- 顶部导航：Logo、支持平台、AI 功能、会员权益、登录、开通会员。
- Hero 工具区：链接输入、粘贴按钮、解析按钮、状态提示。
- 解析结果区：封面、标题、作者、时长、平台、格式选择、下载按钮。
- 高级能力区：视频总结、字幕翻译、音频提取、批量下载。
- 会员套餐弹窗：免费版、Pro、团队版。
- 内容卡片区：热门平台、使用场景、会员权益、FAQ。

## 错误处理

- 无效链接：请输入正确的视频链接。
- 分享文案：后端会自动提取文本中的第一个 `http/https` 链接。
- 平台要求 Cookie：返回 428，提示配置 `YTDLP_COOKIE_FILE`。
- 私密或登录限制：该内容可能需要登录或权限，当前演示版暂不支持。
- 平台限制或失效：平台限制或链接已失效，建议更换链接重试。
- yt-dlp 缺失：提示安装依赖。
- ffmpeg 缺失：基础下载可用，部分高清合并格式不可用。
- 未开放功能：返回 `coming_soon`，前端展示会员能力或即将开放。

## 扩展预留

第二阶段付费闭环：

- 增加数据库。
- 增加用户、套餐、订单、支付回调。
- 增加会员权限和免费额度。

第三阶段 AI 增值：

- 接第三方 AI 接口。
- 视频总结优先基于字幕；无字幕时接音频转写。
- 字幕翻译支持双语字幕下载。
- AI 任务需要队列、成本统计和失败重试。

第四阶段线上化：

- Docker 部署。
- 后台任务队列。
- 临时文件和缓存清理。
- 服务器带宽、并发、日志和监控。

## 测试策略

- 后端用 pytest 覆盖 URL 校验、套餐、能力、AI 占位、错误映射。
- 前端用 TypeScript 检查和生产构建验证。
- 集成时用公开可下载链接验证解析与下载。
- 视觉验收覆盖桌面和手机宽度。

## 合规边界

项目只面向公开或用户有权访问的视频内容。首版不提供 DRM 绕过、破解、盗取登录态、规避会员墙或下载私密内容的能力。页面文案应强调便利性和生产力，不承诺违规下载能力。
## 当前平台兜底策略

- 通用站点仍优先走 `yt-dlp`，所有调用集中在 `app/services/ytdlp_service.py`，方便后续增加队列、限流、会员权限和缓存。
- B 站兜底由 `app/services/bilibili_fallback.py` 实现：公开页面可访问但 `yt-dlp` 触发 412 时，读取页面初始状态获取 `bvid/cid`，再调用 B 站 HTML5 播放地址接口拿 mp4 地址。下载交付使用后端中转，避免客户端缺少 Referer 导致下载失败。
- 抖音兜底由 `app/services/douyin_fallback.py` 实现：先解析短链跳转并提取 `aweme_id`，再调用解析源获取 `video.cdn_url` 或 `video.video_url`。默认解析源为 `https://api.mmp.cc/api/Jiexi`；生产环境建议通过 `DOUYIN_RESOLVER_ENDPOINT` 配置自建签名解析服务或商业 API，多个解析源可用英文逗号分隔。
- 抖音方案不读取用户浏览器 Cookie，不要求用户手动填写 Cookie，也不使用公共共享账号。图集或非视频内容返回 422，提示首版只支持视频下载。
- 当前端请求 `delivery=direct` 时，B 站兜底仍返回 `proxy` 类型和 `/api/download/file` 地址；抖音兜底返回短时有效的 `direct` 直链。

## 当前验收烟测

`web/scripts/e2e-smoke.mjs` 会通过前端同源 `/api` 路径验证：

- B 站公开视频解析为 `BiliBiliFallback`，格式包含 `bili-html5-16`，并能通过后端中转下载真实文件字节。
- 抖音公开视频解析为 `DouyinResolver`，格式为 `douyin-resolver-best`，并能通过返回直链采样下载真实文件字节。
- 可用环境变量 `E2E_DOUYIN_URL` 替换抖音验收链接。

## 当前浏览器交互策略

- 封面图片统一走 `/api/media/thumbnail` 代理。原因是 B 站、抖音等平台图片 CDN 常有 Referer 防盗链，浏览器直接加载平台图片会出现裂图；后端代理可以补充平台 Referer 并缓存短时间结果。
- 下载交付统一优先返回同源 `/api/download/file`。B 站和抖音兜底链路都由后端中转，前端用临时 `<a download>` 触发浏览器下载，不再 `window.open` 新标签页。
- 对通用 `yt-dlp` 直链，前端仍可接收 `direct` 类型，但交互层使用同一个 `<a download>` 触发方式，避免出现 `about:blank` 空白页。
- 烟测需要覆盖：封面代理至少返回 100 字节；下载代理至少返回 100 字节；返回类型符合平台预期。

## 抖音无封面兜底与格式策略

- 当前默认抖音解析源可能只返回 `video.cdn_url` 和 `video.video_url`，不保证返回 `cover`。因此前端在 `thumbnail` 为空时使用视频预览流作为封面兜底。
- 视频预览接口 `/api/media/video-preview` 是预览专用接口，支持浏览器 `Range` 请求；当请求没有明确结束位置时，后端会限制默认返回窗口，避免卡片预览消耗完整视频带宽。
- 抖音格式列表由解析源返回的多个视频 URL 动态生成，当前优先级为 `cdn_url`、`video_url`、下载源、备用源、嵌套播放源。
- 后端对每个抖音视频 URL 使用 HEAD 探测文件大小，并填充到 `VideoFormat.filesize`，让前端下拉框显示真实 MB 数值。

## FFmpeg 策略

- 后端通过 `Settings.ffmpeg_location_path` 统一定位 FFmpeg。
- 优先使用 `FFMPEG_LOCATION` 环境变量，方便生产环境或自定义安装路径。
- 未配置环境变量时，自动使用项目内置路径 `tools/ffmpeg/bin`，该目录需要同时包含 `ffmpeg.exe` 和 `ffprobe.exe`。
- `YtDlpService.runtime_status()` 会把内置 FFmpeg 计入健康检查。
- Python API 调用 yt-dlp 时通过 `ffmpeg_location` 传入路径；子进程调用 yt-dlp 时通过 `--ffmpeg-location` 传入路径。
- 该策略避免依赖系统 PATH，降低新机器启动项目时“能解析但不能合并高清格式”的概率。
