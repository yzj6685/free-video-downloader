# 项目总结

## 当前状态

《一手遮天视频下载总结器》已经完成视频下载、AI 总结、登录注册、免费次数、Stripe 支付和 Pro 权益闭环。

当前本地服务：

- 前端：`http://127.0.0.1:5174`
- 后端：`http://127.0.0.1:8002`

## 已完成能力

- 单链接公开视频解析与下载。
- URL 输入兼容：支持 `https://...`、`www.xxx.com/...`、`xxx.com/...` 和分享文案中的链接。
- B 站公开视频兜底解析、字幕提取、封面代理和后端中转下载。
- 抖音公开视频兜底解析、多格式展示、视频预览、大小探测和 ASR 转写。
- DeepSeek AI 总结：摘要、大纲、知识点、字幕文本、思维导图和视频问答。
- SiliconFlow ASR：抖音等无公开字幕视频可通过音频转写生成真实字幕。
- 登录、注册、会话恢复和退出登录。
- 免费账号 3 次 AI 视频总结额度。
- Stripe Checkout 一次性购买 Pro。
- Stripe webhook 写入本地 SQLite 权益。
- Pro 会员 AI 视频总结不限次数。
- 已开通 Pro 时防止重复支付。
- 前端会员弹窗、套餐展示、支付回跳、权益刷新和错误提示。
- SEO/GEO 相关公开文件和结构化数据。

## 关键接口

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `POST /api/probe`
- `POST /api/download`
- `GET /api/download/file`
- `GET /api/media/thumbnail`
- `GET /api/media/video-preview`
- `GET /api/billing/plans`
- `GET /api/billing/entitlement`
- `POST /api/billing/checkout`
- `POST /api/billing/webhook`
- `POST /api/ai/analyze`
- `POST /api/ai/analyze-stream`
- `POST /api/ai/chat`
- `POST /api/ai/chat-stream`

## 关键文件

- `api/app/models.py`：请求/响应模型和 URL 兼容提取。
- `api/app/routers/auth.py`：登录注册路由。
- `api/app/routers/billing.py`：套餐、权益、Checkout 和 webhook 路由。
- `api/app/routers/ai_analysis.py`：AI 总结和问答路由，按登录账号校验权益。
- `api/app/services/auth_service.py`：本地账号、密码哈希和会话。
- `api/app/services/billing_service.py`：Stripe、订单、权益、免费次数和防重复支付。
- `api/app/services/ytdlp_service.py`：yt-dlp 解析和下载交付。
- `api/app/services/bilibili_fallback.py`：B 站兜底解析和字幕。
- `api/app/services/douyin_fallback.py`：抖音兜底解析。
- `api/app/services/asr_service.py`：SiliconFlow ASR。
- `api/app/services/ai_analysis_service.py`：AI 总结、缓存、导图和问答上下文。
- `web/src/App.vue`：主页面、登录、支付、会员、下载和 AI 工作台。
- `web/src/api.ts`：前端 API 调用。
- `web/src/types.ts`：前端类型。

## 验证结果

最近一次验证：

- 后端测试：`45 passed`
- 前端类型检查：通过
- 前端生产构建：通过
- `git diff --check`：通过，仅有 Windows 换行提示
- 前后端健康检查：通过

## 运行方式

后端：

```powershell
cd api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

前端：

```powershell
cd web
$env:VITE_API_PROXY_TARGET="http://127.0.0.1:8002"
npm run dev:local
```

## 环境变量

使用根目录 `.env` 保存本地密钥；使用 `.env.example` 查看变量模板。

重要变量：

- `DEEPSEEK_API_KEY`
- `SILICONFLOW_API_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `APP_PUBLIC_URL`
- `BILLING_DB_PATH`

## 合规边界

项目只面向公开或用户有权访问的视频内容。不提供 DRM 绕过、破解、会员墙绕过、私密内容下载、公共账号 Cookie 注入等能力。
