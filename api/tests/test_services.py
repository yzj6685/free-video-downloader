from fastapi import HTTPException

from app.services.billing_service import get_plans
from app.services.capabilities_service import get_capabilities
from app.services.asr_service import AsrService
from app.services.douyin_fallback import DouyinFallbackService
from app.services.ytdlp_service import YtDlpService


def test_billing_plans_include_pro_membership():
    plans = get_plans().plans
    assert len(plans) == 2
    assert any(plan.id == "pro" for plan in plans)
    pro = next(plan for plan in plans if plan.id == "pro")
    assert any(feature.label == "无限 AI 视频总结" for feature in pro.features)
    assert not any(feature.label == "字幕翻译" for feature in pro.features)


def test_capabilities_mark_current_features_as_available():
    capabilities = get_capabilities()
    statuses = {item.key: item.status for item in capabilities.items}
    assert statuses["single_link_download"] == "available"
    assert statuses["ai_video_analysis"] == "available"
    assert "subtitle_translate" not in statuses
    assert "DRM" in capabilities.compliance_note


def test_cookie_required_error_is_actionable():
    error = YtDlpService()._map_error(Exception("Fresh cookies are needed"))

    assert error.status_code == 428
    assert "YTDLP_COOKIE_FILE" in error.detail


def test_douyin_short_link_id_extraction_is_supported(monkeypatch):
    service = DouyinFallbackService()

    class FakeResponse:
        headers = {"location": "https://www.iesdouyin.com/share/video/7641894056389348649/?from=web_code_link"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr("app.services.douyin_fallback.httpx.Client", FakeClient)

    resolved, aweme_id = service._resolve_url_and_id("https://v.douyin.com/CGJkObXBEcs")

    assert "iesdouyin.com/share/video" in resolved
    assert aweme_id == "7641894056389348649"


def test_douyin_public_resolver_payload_is_normalized():
    service = DouyinFallbackService()
    service._probe_filesize = lambda media_url: 123456
    payload = {
        "code": 200,
        "type": "视频",
        "desc": "公开视频标题",
        "author": {"nickname": "作者"},
        "video": {
            "cdn_url": "https://example.com/cdn.mp4",
            "video_url": "https://example.com/play.mp4",
        },
    }

    result = service._normalize_probe("https://v.douyin.com/demo/", payload, "123")

    assert result.extractor == "DouyinResolver"
    assert result.title == "公开视频标题"
    assert result.uploader == "作者"
    assert result.recommended_format_id == "douyin-resolver-cdn"
    assert [item.format_id for item in result.formats] == ["douyin-resolver-cdn", "douyin-resolver-play"]
    assert all(item.filesize == 123456 for item in result.formats)


def test_douyin_share_page_fallback_is_used_when_public_resolver_has_no_url(monkeypatch):
    service = DouyinFallbackService()
    service._probe_filesize = lambda media_url: 987654

    monkeypatch.setattr(service, "_resolver_endpoints", lambda: ["https://resolver.example"])
    monkeypatch.setattr(
        service,
        "_call_resolver",
        lambda endpoint, resolved_url, aweme_id: {"code": 200, "type": "视频", "desc": ""},
    )
    monkeypatch.setattr(
        service,
        "_call_share_page",
        lambda resolved_url, aweme_id: {
            "code": 200,
            "type": "视频",
            "desc": "分享页标题",
            "author": {"nickname": "作者"},
            "video": {"play_addr": {"url_list": ["https://example.com/share.mp4"]}},
        },
    )

    payload = service._call_resolvers("https://www.iesdouyin.com/share/video/123/", "123")
    result = service._normalize_probe("https://v.douyin.com/demo/", payload, "123")

    assert result.title == "分享页标题"
    assert result.uploader == "作者"
    assert result.recommended_format_id == "douyin-resolver-nested"
    assert result.formats[0].filesize == 987654


def test_asr_text_is_split_into_segments():
    service = AsrService()

    segments = service._segments_from_text("第一句话。第二句话！第三句话？")

    assert [segment.text for segment in segments] == ["第一句话。", "第二句话！", "第三句话？"]
    assert segments[0].start == 0
    assert segments[0].end is not None
    assert segments[1].start == segments[0].end


def test_douyin_metadata_transcript_uses_public_caption(monkeypatch):
    service = DouyinFallbackService()
    monkeypatch.setattr(
        service,
        "_resolve_url_and_id",
        lambda url: ("https://www.iesdouyin.com/share/video/123/", "123"),
    )
    monkeypatch.setattr(
        service,
        "_call_resolvers",
        lambda resolved_url, aweme_id: {
            "code": 200,
            "desc": "你为什么老是不敢承认他们不爱你 #情感 #婚姻",
            "video": {"cdn_url": "https://example.com/cdn.mp4"},
        },
    )

    title, segments = service.metadata_transcript("https://v.douyin.com/demo/")

    assert title == "你为什么老是不敢承认他们不爱你 #情感 #婚姻"
    assert len(segments) == 1
    assert segments[0].start == 0
    assert segments[0].end is None
    assert segments[0].text == "你为什么老是不敢承认他们不爱你 #情感 #婚姻"


def test_douyin_album_payload_is_rejected(monkeypatch):
    service = DouyinFallbackService()

    monkeypatch.setattr(service, "_resolver_endpoints", lambda: ["https://resolver.example"])
    monkeypatch.setattr(
        service,
        "_call_resolver",
        lambda endpoint, resolved_url, aweme_id: {"code": 200, "type": "图集", "desc": "不是视频"},
    )

    try:
        service._call_resolvers("https://www.iesdouyin.com/share/video/123/", "123")
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "图集" in exc.detail
    else:
        raise AssertionError("Expected Douyin album payload to be rejected")
