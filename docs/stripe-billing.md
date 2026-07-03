# Stripe 支付接入说明

## 当前实现

支付功能使用 Stripe Checkout 做 Pro 一次性购买，默认商品为 `一手遮天视频下载总结器 Pro`，默认价格为 `CNY 19.90`。

支付成功后，Stripe webhook 会写入本地 SQLite 数据库，并按登录账号邮箱开通 Pro 权益。免费账号可体验 3 次 AI 视频总结；Pro 账号 AI 视频总结、视频问答、字幕整理和思维导图不限次数。

系统同时做了两层重复支付保护：

- 前端：当前登录账号已是 Pro 时，点击开通会提示“你已经是 Pro 会员，无需重复开通”。
- 后端：已开通 Pro 的邮箱再次创建 Checkout 会返回 `409`。

## 环境变量

推荐在项目根目录 `.env` 中配置：

```powershell
APP_PUBLIC_URL="http://127.0.0.1:5174"
STRIPE_SECRET_KEY="sk_test_xxx"
STRIPE_WEBHOOK_SECRET="whsec_xxx"
STRIPE_PRODUCT_NAME="一手遮天视频下载总结器 Pro"
STRIPE_PRICE_CURRENCY="cny"
STRIPE_PRICE_AMOUNT="1990"
BILLING_DB_PATH="C:\code\ai-code\free-video-downloader\api\billing.sqlite3"
```

说明：

- `STRIPE_PRICE_AMOUNT` 使用最小货币单位，`1990` 表示人民币 19.90 元。
- `APP_PUBLIC_URL` 用于生成 Checkout 成功/取消后的回跳地址。
- `.env` 不应提交到 Git。

## 本地 webhook 调试

1. 安装并登录 Stripe CLI。

```powershell
stripe login
```

2. 启动后端。

```powershell
cd C:\code\ai-code\free-video-downloader\api
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8002
```

3. 另开终端转发 Stripe webhook。

```powershell
stripe listen --forward-to localhost:8002/api/billing/webhook
```

4. 复制 CLI 输出里的 `whsec_...`，写入 `.env` 的 `STRIPE_WEBHOOK_SECRET`，然后重启后端。

## 前端验收路径

1. 打开 `http://127.0.0.1:5174`。
2. 注册或登录账号。
3. 点击 `开通会员` 或 Pro 套餐卡片。
4. 跳转 Stripe Checkout。
5. 使用 Stripe 测试卡付款：

```text
卡号：4242 4242 4242 4242
日期：任意未来日期
CVC：任意 3 位
邮编：任意
```

6. 支付成功回到首页后，当前登录账号应显示 Pro 已开通。
7. 再次点击 Pro 开通入口，应提示已是 Pro，不应重复跳转支付。
8. 解析视频后，AI 总结和视频问答应可正常使用。

## 上线注意事项

- 切换正式 `sk_live_...` 密钥。
- 在 Stripe Dashboard 配置线上 webhook endpoint。
- 确认生产 `APP_PUBLIC_URL` 为正式 HTTPS 域名。
- 为 SQLite 或正式数据库做好备份策略。
- 不要提交 `.env` 或任何真实密钥。
