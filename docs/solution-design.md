# 方案设计文档

## 总体架构

项目采用前后端分离：

- `web/`：Vue 3 + Vite + TypeScript + Tailwind CSS，负责页面交互、登录、会员弹窗、下载工作台和 AI 总结工作台。
- `api/`：FastAPI，负责视频解析、下载交付、账号认证、支付权益、AI 总结和平台兜底服务。
- `docs/`：记录需求、设计、支付接入和项目总结。

本地状态使用 SQLite 保存：

- 用户账号和会话。
- Stripe 支付订单。
- Pro 会员权益。
- 免费 AI 总结使用次数。

## 核心流程

### 视频解析下载

1. 用户粘贴视频链接或分享文案。
2. 后端从文本中提取第一个 URL；无协议域名自动补 `https://`。
3. `POST /api/probe` 调用 yt-dlp 或平台兜底服务解析视频信息。
4. 前端展示标题、作者、封面/预览、格式和文件大小。
5. 用户选择格式并点击下载。
6. 后端优先返回同源下载入口，必要时通过 `/api/download/file` 中转。

### AI 总结

1. 用户登录后解析视频。
2. 前端自动调用 `POST /api/ai/analyze-stream`。
3. 后端根据登录 token 读取账号邮箱。
4. 计费服务判断该账号是否 Pro，或是否仍有免费 3 次额度。
5. 字幕服务优先提取平台字幕；无字幕时可用 SiliconFlow ASR 转写音频。
6. AI 服务调用 DeepSeek 生成 Markdown 摘要、大纲、知识点和建议问题。
7. 前端流式展示摘要，并生成字幕文本、思维导图和视频问答入口。
8. 非 Pro 用户在分析成功后扣减免费次数。

### 支付会员

1. 用户登录账号。
2. 点击 Pro 套餐。
3. 前端先刷新权益；已是 Pro 则提示无需重复开通。
4. 后端 `POST /api/billing/checkout` 再次检查是否已是 Pro。
5. 未开通时创建 Stripe Checkout Session。
6. 支付成功后 Stripe webhook 调用 `/api/billing/webhook`。
7. 后端记录订单并写入 Pro 权益。
8. 前端回跳首页后刷新当前账号权益。

## 后端模块

- `app/main.py`：FastAPI 应用、CORS 和路由注册。
- `app/models.py`：请求/响应模型，包含 URL 提取兼容逻辑。
- `app/routers/video.py`：健康检查、解析、下载、封面和预览接口。
- `app/routers/auth.py`：注册、登录、当前用户和退出登录。
- `app/routers/billing.py`：套餐、权益、Checkout 和 webhook。
- `app/routers/ai_analysis.py`：AI 总结和视频问答。
- `app/services/ytdlp_service.py`：yt-dlp 封装和下载交付。
- `app/services/bilibili_fallback.py`：B 站兜底解析与字幕。
- `app/services/douyin_fallback.py`：抖音兜底解析。
- `app/services/subtitle_service.py`：字幕选择、下载和解析。
- `app/services/asr_service.py`：SiliconFlow ASR。
- `app/services/deepseek_client.py`：DeepSeek API 封装。
- `app/services/ai_analysis_service.py`：AI 总结编排、缓存和问答上下文。
- `app/services/auth_service.py`：SQLite 用户、密码哈希和会话 token。
- `app/services/billing_service.py`：套餐、Stripe、订单、权益和免费次数。

## 前端模块

- `web/src/App.vue`：单页主界面。
- `web/src/api.ts`：API 封装，AI 请求带登录 token。
- `web/src/types.ts`：类型定义。
- `web/public/llms.txt`：AI agent 可读的产品说明。
- `web/public/ai-overview.md`：AI 检索友好的 Markdown 说明。
- `web/public/humans.txt`：站点实体和合规说明。

## 权益模型

套餐只有两档：

- 免费版：公开视频解析下载免费，AI 视频总结免费体验 3 次。
- Pro 会员：一次性购买，AI 视频总结不限次数。

约束：

- 免费次数和 Pro 权益都绑定登录账号邮箱。
- 未登录不能调用 AI 总结接口。
- 前端传入的 `billing_email` 不作为 AI 权益依据；后端只信任登录 token。
- 已开通 Pro 的账号不能重复创建 Stripe Checkout。

## 数据表

SQLite 默认路径：`api/billing.sqlite3`。

主要表：

- `users`
- `auth_sessions`
- `billing_orders`
- `billing_entitlements`
- `ai_usage`

## 配置

项目会读取根目录 `.env` 和 `api/.env`，且不覆盖已存在的系统环境变量。

关键变量：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`
- `SILICONFLOW_API_KEY`
- `ASR_PROVIDER`
- `SILICONFLOW_ASR_MODEL`
- `ASR_MAX_SECONDS`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `APP_PUBLIC_URL`
- `BILLING_DB_PATH`
- `YTDLP_COOKIE_FILE`
- `FFMPEG_LOCATION`

## 合规边界

项目只面向公开或用户有权访问的视频内容。页面和接口都不承诺也不实现 DRM 绕过、会员墙绕过、私密内容下载、公共账号 Cookie 注入或盗取登录态。

## 验证策略

- 后端：`pytest`
- 前端：`vue-tsc --noEmit`
- 构建：`vite build`
- 运行健康检查：`GET /api/health`
- 支付验收：Stripe CLI webhook + Stripe 测试卡
- AI 验收：登录账号解析视频，确认免费次数扣减；Pro 账号确认不限次数
