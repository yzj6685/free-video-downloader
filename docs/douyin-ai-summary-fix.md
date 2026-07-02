# 抖音 AI 总结修复沉淀

## 背景

抖音公开视频通常不返回平台字幕。此前 AI 总结只能把抖音作品公开 `title/desc` 包装成一条 `transcript_segments`，再交给 DeepSeek 总结。这会导致两个问题：

- 字幕页只显示一条 0:00 文案，不是真实视频对白。
- AI 容易根据标题和话题扩写，出现总结内容与视频实际内容不一致。

本轮修复后，抖音总结优先走真实音频 ASR。未配置 ASR 时才退回公开文案兜底。

## 当前链路

```text
前端解析抖音链接
  -> POST /api/probe
  -> DouyinFallbackService 解析短链和 aweme_id
  -> 默认公开解析源 / 分享页 ROUTER_DATA 兜底拿视频直链
  -> 前端自动调用 POST /api/ai/analyze-stream
  -> SubtitleService 判断 douyin-resolver-* 格式
  -> AsrService 使用 ffmpeg 抽取 16k 单声道音频
  -> SiliconFlow /v1/audio/transcriptions
  -> 返回真实转写文本并切分成 TranscriptSegment
  -> DeepSeek 基于真实转写生成摘要、字幕、思维导图和问答
```

## 关键文件

- `api/app/services/douyin_fallback.py`
  - 解析抖音短链，提取 `aweme_id`。
  - 调用 `DOUYIN_RESOLVER_ENDPOINT` 或默认公开解析源。
  - 当解析源“成功但无视频地址”时，读取分享页 `window._ROUTER_DATA`，兼容 `video.play_addr.url_list` 与 `video.bit_rate[].play_addr.url_list`。
  - 仍保留 `metadata_transcript()` 作为未配置 ASR 时的公开文案兜底。

- `api/app/services/asr_service.py`
  - 当前只实现 SiliconFlow provider。
  - 使用 ffmpeg 将视频直链抽取为 `mp3`：16k、单声道、48k。
  - 调用 `https://api.siliconflow.cn/v1/audio/transcriptions`。
  - 默认模型：`FunAudioLLM/SenseVoiceSmall`。
  - 单文件遵循 SiliconFlow 限制：不超过 1 小时、50MB；项目默认 `ASR_MAX_SECONDS=900`。

- `api/app/services/subtitle_service.py`
  - 抖音链接或 `douyin-resolver-*` 格式优先调用 `AsrService`。
  - ASR 未配置时退回 `DouyinFallbackService.metadata_transcript()`。
  - B 站等已有平台字幕链路不受影响。

- `api/app/services/ai_analysis_service.py`
  - SSE 增加阶段状态：
    - `stage=asr progress=12`
    - `stage=summary progress=88`
  - 前端可以在 ASR 阻塞期间显示可感知进度。

- `web/src/App.vue`
  - AI 等待态新增进度条、百分比和阶段列表。
  - 三个阶段：读取字幕、音频转写、生成摘要。
  - 抖音 ASR 等待文案明确提示“视频越长等待越久，转写后摘要会流式出现”。

## 环境变量

不要把真实 Key 写入代码、文档或 Git。

```powershell
$env:SILICONFLOW_API_KEY="你的 SiliconFlow API Key"
$env:ASR_PROVIDER="siliconflow"
$env:SILICONFLOW_ASR_MODEL="FunAudioLLM/SenseVoiceSmall"
$env:ASR_MAX_SECONDS="900"
```

DeepSeek 仍需要：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
$env:DEEPSEEK_BASE_URL="https://api.deepseek.com"
$env:DEEPSEEK_MODEL="deepseek-v4-pro"
```

## 验证结果

已完成以下验证：

- SiliconFlow 最小音频连通性测试：成功。
- 真实抖音视频 ASR：成功，从 1 条标题文案变为 38 段真实转写。
- `POST /api/ai/analyze-stream`：成功返回 `transcript_ready` 和 `complete`。
- 后端全量测试：`31 passed`。
- 前端类型检查：通过。
- 前端生产构建：通过。
- `web/scripts/e2e-smoke.mjs`：B 站与抖音解析、下载、预览通过。

## 已知边界

- 当前 ASR 兜底只接入抖音 `douyin-resolver-*` 链路。
- ASR 会增加等待时间和调用成本。当前通过前端阶段进度降低用户等待焦虑。
- 后续可增加字幕缓存：同一视频 URL 或 aweme_id 的 ASR 结果缓存起来，二次分析可直接复用。
- 生产上线建议加入任务队列、并发限制、成本统计和会员额度控制。

