# 本地运行指南

这份文档用于从零启动项目，适合第一次克隆仓库后的本地体验和功能验收。

## 1. 前置条件

- Python 3.10+
- Node.js 18+
- npm
- ffmpeg（推荐安装，用于高清音视频合并和无字幕视频的音频转写）

如果只是先打开页面、体验普通链接解析，可以暂时跳过 ffmpeg；但下载某些高清合并格式、或使用 ASR 从视频中提取音频时需要它。

Windows 用户可以在克隆项目后运行仓库自带脚本：

```powershell
.\scripts\install-ffmpeg.ps1
```

这个脚本会下载 ffmpeg，并安装到项目目录：

```text
tools/ffmpeg/bin/ffmpeg.exe
tools/ffmpeg/bin/ffprobe.exe
```

后端会自动识别这个目录，不需要手动加入系统 PATH。也可以自己安装 ffmpeg，并在 `.env` 中指定：

```text
FFMPEG_LOCATION=C:\path\to\ffmpeg\bin
```

验证 ffmpeg 是否可用：

```powershell
.\tools\ffmpeg\bin\ffmpeg.exe -version
.\tools\ffmpeg\bin\ffprobe.exe -version
```

macOS / Linux 用户可以用系统包管理器安装，例如：

```bash
brew install ffmpeg
```

或：

```bash
sudo apt install ffmpeg
```

## 2. 克隆项目

```powershell
git clone https://github.com/yzj6685/download-any-video-ai.git
cd download-any-video-ai
```

## 3. 配置环境变量

复制示例配置：

```powershell
Copy-Item .env.example .env
```

常用配置：

```text
APP_PUBLIC_URL=http://127.0.0.1:5174
DEEPSEEK_API_KEY=your_deepseek_api_key
SILICONFLOW_API_KEY=your_siliconflow_api_key
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
```

只体验视频解析下载时，可以先不配置 AI 和 Stripe 密钥；使用 AI 总结、ASR、支付时再补齐对应配置。

## 4. 启动后端

```powershell
cd api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8002
```

后端健康检查：

```text
http://127.0.0.1:8002/api/health
```

## 5. 启动前端

新开一个终端：

```powershell
cd web
npm install
$env:VITE_API_PROXY_TARGET="http://127.0.0.1:8002"
npm run dev:local
```

访问页面：

```text
http://127.0.0.1:5174
```

## 6. 验证视频解析

1. 打开首页。
2. 粘贴一个你有权访问和保存的公开视频链接。
3. 点击“解析”。
4. 查看标题、封面、格式列表和下载入口。

如果解析失败，优先确认：

- 链接是否为公开视频。
- 当前网络是否能访问目标平台。
- 后端是否安装好 `yt-dlp` 和 `ffmpeg`。
- 平台是否临时调整了页面结构或访问策略。

## 7. 验证 AI 总结

1. 配置 `DEEPSEEK_API_KEY`。
2. 如果视频没有平台字幕，可配置 `SILICONFLOW_API_KEY`。
3. 注册并登录站内账号。
4. 解析视频后触发 AI 总结。
5. 查看摘要、大纲、字幕文本、思维导图和问答入口。

## 8. 验证 Stripe 支付

安装并登录 Stripe CLI 后，启动 webhook 转发：

```powershell
stripe listen --forward-to localhost:8002/api/billing/webhook
```

把 CLI 输出的 `whsec_...` 写入 `.env` 的 `STRIPE_WEBHOOK_SECRET`，重启后端，然后在页面中点击 Pro 套餐并使用 Stripe 测试卡完成支付。

更多支付细节见 [Stripe 支付接入说明](stripe-billing.md)。

## 9. 运行测试

后端测试：

```powershell
cd api
.\.venv\Scripts\python.exe -m pytest
```

前端类型检查和构建：

```powershell
cd web
npm run typecheck
npm run build
```

## 10. 常见问题

### 前端请求不到后端

确认前端启动前设置了：

```powershell
$env:VITE_API_PROXY_TARGET="http://127.0.0.1:8002"
```

并确认后端监听端口是 `8002`。

### 浏览器出现跨域问题

本项目默认放行：

- `http://127.0.0.1:5173`
- `http://localhost:5173`
- `http://127.0.0.1:5174`
- `http://localhost:5174`

如果你使用了其他端口，需要在 `api/app/main.py` 的 CORS 配置中补充。

### AI 总结没有结果

确认：

- 已登录账号。
- `DEEPSEEK_API_KEY` 已配置并且可用。
- 视频存在字幕，或已经配置可用的 ASR 服务。
- 后端日志中没有模型额度、网络或鉴权错误。

### 支付成功但权益没更新

确认：

- Stripe CLI 正在转发 webhook。
- `.env` 中的 `STRIPE_WEBHOOK_SECRET` 和 CLI 输出一致。
- 后端已重启并加载最新环境变量。
- 当前登录账号邮箱和支付流程绑定的邮箱一致。
