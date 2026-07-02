import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.models import AiAnalysisResponse, TranscriptSegment
from app.services.ai_analysis_service import CachedAnalysis, ai_analysis_service
from app.services.bilibili_fallback import BilibiliFallbackService
from app.services.subtitle_service import SubtitleService, SubtitleTrack


client = TestClient(app)


def test_parse_vtt_subtitles():
    content = """WEBVTT

00:00:01.000 --> 00:00:03.000
第一句字幕

00:00:04.500 --> 00:00:06.000
第二句字幕
"""

    segments = SubtitleService()._parse("vtt", content)

    assert len(segments) == 2
    assert segments[0].start == 1
    assert segments[0].end == 3
    assert segments[0].text == "第一句字幕"


def test_parse_srt_subtitles():
    content = """1
00:00:01,000 --> 00:00:03,000
第一句字幕

2
00:00:04,500 --> 00:00:06,000
第二句字幕
"""

    segments = SubtitleService()._parse("srt", content)

    assert len(segments) == 2
    assert segments[1].start == 4.5
    assert segments[1].text == "第二句字幕"


def test_parse_json3_subtitles():
    content = """
{
  "events": [
    {"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "第一句"}, {"utf8": "字幕"}]},
    {"tStartMs": 4000, "dDurationMs": 1000, "segs": [{"utf8": "第二句字幕"}]}
  ]
}
"""

    segments = SubtitleService()._parse("json3", content)

    assert len(segments) == 2
    assert segments[0].start == 1
    assert segments[0].end == 3
    assert segments[0].text == "第一句字幕"


def test_playlist_segment_urls_are_resolved():
    content = """#EXTM3U
#EXTINF:30.0000,
zh-cn.vtt?segment=0&duration=30
#EXTINF:30.0000,
https://cdn.example.com/subtitles/zh-cn.vtt?segment=1
"""

    urls = SubtitleService()._playlist_segment_urls("https://example.com/path/master.m3u8", content)

    assert urls == [
        "https://example.com/path/zh-cn.vtt?segment=0&duration=30",
        "https://cdn.example.com/subtitles/zh-cn.vtt?segment=1",
    ]


def test_clean_text_removes_non_breaking_space_only_segment():
    assert SubtitleService()._clean_text("\xa0") == ""


def test_parse_bilibili_subtitle_body():
    payload = {
        "body": [
            {"from": 0.5, "to": 2.5, "content": "第一句字幕"},
            {"from": 3, "to": 5, "content": "第二句字幕"},
        ]
    }

    segments = BilibiliFallbackService()._parse_subtitle_body(payload)

    assert len(segments) == 2
    assert segments[0].start == 0.5
    assert segments[0].text == "第一句字幕"


def test_subtitle_extract_uses_bilibili_fallback_when_ytdlp_fails(monkeypatch):
    def fake_fallback(url: str, language: str):
        return "B站测试视频", [TranscriptSegment(start=0, end=2, text="B站字幕")]

    service = SubtitleService()
    monkeypatch.setattr(
        service,
        "_extract_info",
        lambda url: (_ for _ in ()).throw(HTTPException(status_code=502, detail="yt-dlp blocked")),
    )
    monkeypatch.setattr("app.services.subtitle_service.bilibili_fallback_service.can_handle", lambda url: True)
    monkeypatch.setattr("app.services.subtitle_service.bilibili_fallback_service.subtitles", fake_fallback)

    async def run():
        return await service.extract("https://www.bilibili.com/video/BVtest", "zh")

    title, segments = asyncio.run(run())

    assert title == "B站测试视频"
    assert segments[0].text == "B站字幕"


def test_subtitle_extract_uses_douyin_metadata_when_subtitles_missing(monkeypatch):
    def fake_metadata_transcript(url: str):
        return "抖音公开视频标题", [TranscriptSegment(start=0, end=None, text="抖音公开视频文案")]

    service = SubtitleService()
    monkeypatch.setattr(service, "_extract_info", lambda url: {"title": "yt-dlp 标题", "subtitles": {}, "automatic_captions": {}})
    monkeypatch.setattr("app.services.subtitle_service.douyin_fallback_service.can_handle", lambda url: True)
    monkeypatch.setattr("app.services.subtitle_service.douyin_fallback_service.metadata_transcript", fake_metadata_transcript)

    async def run():
        return await service.extract("https://v.douyin.com/demo/", "zh", "douyin-resolver-cdn")

    title, segments = asyncio.run(run())

    assert title == "抖音公开视频标题"
    assert segments[0].text == "抖音公开视频文案"


def test_subtitle_selection_prefers_manual_chinese():
    service = SubtitleService()
    info = {
        "subtitles": {
            "en": [{"url": "https://example.com/en.vtt", "ext": "vtt"}],
            "zh-CN": [{"url": "https://example.com/zh.vtt", "ext": "vtt"}],
        },
        "automatic_captions": {
            "zh-CN": [{"url": "https://example.com/auto.vtt", "ext": "vtt"}],
        },
    }

    track = service._select_track(info, "zh")

    assert isinstance(track, SubtitleTrack)
    assert track.url == "https://example.com/zh.vtt"
    assert track.automatic is False


def test_ai_analyze_route_returns_structured_result(monkeypatch):
    async def fake_extract(url: str, language: str, format_id: str = "best"):
        assert format_id == "douyin-resolver-cdn"
        return "测试视频", [
            TranscriptSegment(start=0, end=2, text="这是第一段知识点"),
            TranscriptSegment(start=2, end=4, text="这是第二段结论"),
        ]

    async def fake_stream_text(messages, max_tokens=2048):
        yield "## 视频概述\n这是测试摘要\n\n"
        yield "## 内容大纲\n1. **开场** [00:00]\n"
        yield "   • **主题说明**：介绍主题\n"

    monkeypatch.setattr("app.services.ai_analysis_service.subtitle_service.extract", fake_extract)
    monkeypatch.setattr("app.services.ai_analysis_service.deepseek_client.stream_text", fake_stream_text)

    response = client.post("/api/ai/analyze", json={"url": "https://example.com/video", "format_id": "douyin-resolver-cdn"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "测试视频"
    assert "这是测试摘要" in payload["summary"]
    assert "[00:00]" not in payload["summary"]
    assert "•" not in payload["summary"]
    assert "- **主题说明**：介绍主题" in payload["summary"]
    assert payload["key_points"] == []
    assert payload["outline"][0]["title"] == "开场"
    assert payload["outline"][0]["start"] is None
    assert payload["suggested_questions"] == []
    assert payload["analysis_id"]


def test_ai_analyze_stream_route_returns_sse_events(monkeypatch):
    async def fake_analyze_stream(url: str, language: str, format_id: str = "best"):
        assert format_id == "douyin-resolver-cdn"
        yield {"type": "status", "message": "正在提取平台字幕..."}
        yield {"type": "summary_delta", "delta": "这是"}
        yield {"type": "summary_delta", "delta": "摘要"}
        yield {
            "type": "complete",
            "analysis": {
                "analysis_id": "stream-test",
                "title": "测试视频",
                "source_url": url,
                "summary": "这是摘要",
                "outline": [],
                "key_points": [],
                "transcript_segments": [],
                "suggested_questions": [],
                "model": "test-model",
                "created_at": datetime.now(UTC).isoformat(),
            },
        }

    monkeypatch.setattr("app.routers.ai_analysis.ai_analysis_service.analyze_stream", fake_analyze_stream)

    response = client.post("/api/ai/analyze-stream", json={"url": "https://example.com/video", "format_id": "douyin-resolver-cdn"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert '"type": "status"' in body
    assert '"type": "summary_delta"' in body
    assert '"type": "complete"' in body
    assert "这是摘要" in body


def test_ai_chat_route_answers_from_cached_analysis(monkeypatch):
    analysis = AiAnalysisResponse(
        analysis_id="analysis-test",
        title="测试视频",
        source_url="https://example.com/video",
        summary="这是测试摘要",
        outline=[],
        key_points=["知识点一"],
        transcript_segments=[TranscriptSegment(start=0, end=2, text="知识点一说明")],
        suggested_questions=[],
        model="test-model",
        created_at=datetime.now(UTC).isoformat(),
    )
    ai_analysis_service._cache["analysis-test"] = CachedAnalysis(
        response=analysis,
        transcript_text="[00:00] 知识点一说明",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    async def fake_complete_text(messages, max_tokens=2048):
        return "这是问答结果"

    monkeypatch.setattr("app.services.ai_analysis_service.deepseek_client.complete_text", fake_complete_text)

    response = client.post(
        "/api/ai/chat",
        json={"analysis_id": "analysis-test", "question": "知识点一是什么？"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "这是问答结果"


def test_ai_chat_route_requires_existing_analysis():
    response = client.post(
        "/api/ai/chat",
        json={"analysis_id": "missing", "question": "讲了什么？"},
    )

    assert response.status_code == 404
    assert "重新分析" in response.json()["detail"]


def test_ai_chat_stream_route_returns_sse_events(monkeypatch):
    analysis = AiAnalysisResponse(
        analysis_id="analysis-stream-test",
        title="测试视频",
        source_url="https://example.com/video",
        summary="这是测试摘要",
        outline=[],
        key_points=[],
        transcript_segments=[TranscriptSegment(start=0, end=2, text="第一段字幕")],
        suggested_questions=[],
        model="test-model",
        created_at=datetime.now(UTC).isoformat(),
    )
    ai_analysis_service._cache["analysis-stream-test"] = CachedAnalysis(
        response=analysis,
        transcript_text="[00:00] 第一段字幕",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    async def fake_stream_text(messages, max_tokens=2048):
        yield "这是"
        yield "流式回答"

    monkeypatch.setattr("app.services.ai_analysis_service.deepseek_client.stream_text", fake_stream_text)

    response = client.post(
        "/api/ai/chat-stream",
        json={"analysis_id": "analysis-stream-test", "question": "讲了什么？"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert '"type": "related_segments"' in body
    assert '"type": "answer_delta"' in body
    assert "流式回答" in body
    assert '"type": "complete"' in body
