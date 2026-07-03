# B 站 AI 字幕获取策略

当前 AI 视频分析一期仍以“平台已有字幕”为主，不伪造视频内容，也不绕过平台权限。

## 获取顺序

1. 优先通过 yt-dlp 读取公开视频的手工字幕和自动字幕。
2. yt-dlp 被 B 站 412 等校验拦截时，进入 `BilibiliFallbackService`。
3. fallback 先读取页面初始状态里的 `videoData.subtitle.list`，如果已有 `subtitle_url`，直接抓取字幕正文。
4. 如果页面只暴露字幕记录但 `subtitle_url` 为空，再参考 `liyupi/free-video-downloader` 的实现，请求 `x/v2/dm/view?aid=...&oid=...&type=1` 获取 CC 字幕 / AI 字幕列表。
5. 如果 `x/v2/dm/view` 仍未返回字幕正文，再请求 `x/player/v2` 字幕列表。
6. 未配置 `YTDLP_COOKIE_FILE` 时，后端会自动尝试从本机 Chrome、Edge 读取 B 站登录态 Cookie，再重试字幕接口。

## 仍可能失败的情况

B 站有些视频会在公开视频页面展示“有字幕记录”，但匿名接口不返回字幕正文地址。当前实现已优先使用 `x/v2/dm/view`，它能覆盖 `BV1mAAmzqEfP` 这类页面初始数据里 `subtitle_url` 为空、但弹幕 view 接口可返回字幕正文的公开视频。若该接口也拿不到正文，且 Chrome/Edge 正在运行，Windows 可能锁住 Cookie 数据库，自动读取也会失败。

接口会返回可理解的 422 提示：

> 当前 B 站视频未返回可提取字幕正文。系统已尝试公开字幕接口和本机浏览器登录态；如果网页播放器里能看到字幕，请确认 Chrome/Edge 已登录 B 站，或关闭浏览器后重试。

当前项目已经接入 SiliconFlow ASR。公开视频没有平台字幕时，可在配置 `SILICONFLOW_API_KEY` 后使用音频转写作为 AI 总结兜底。

## 已验证案例

`https://bilibili.com/video/BV1mAAmzqEfP`

- 页面初始数据中存在中文字幕记录，但 `subtitle_url` 为空。
- `x/player/v2` 匿名接口返回空字幕列表。
- `x/v2/dm/view` 返回 `zh`、`ai-zh` 等字幕列表，并提供可访问的 `aisubtitle.hdslb.com` 字幕正文地址。
- 当前项目已验证可提取 114 段字幕，并完成 AI 总结、章节大纲、核心知识点、转录文本和 AI 问答。
