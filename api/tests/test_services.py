from fastapi import HTTPException

from app.services.billing_service import get_plans
from app.services.capabilities_service import get_capabilities
from app.services.douyin_fallback import DouyinFallbackService
from app.services.ytdlp_service import YtDlpService


def test_billing_plans_include_pro_membership():
    plans = get_plans().plans
    assert any(plan.id == "pro" for plan in plans)
    pro = next(plan for plan in plans if plan.id == "pro")
    assert any(feature.label == "视频总结" for feature in pro.features)
    assert any(feature.label == "字幕翻译" for feature in pro.features)


def test_capabilities_mark_ai_features_as_coming_soon():
    capabilities = get_capabilities()
    statuses = {item.key: item.status for item in capabilities.items}
    assert statuses["single_link_download"] == "available"
    assert statuses["video_summary"] == "coming_soon"
    assert statuses["subtitle_translate"] == "coming_soon"
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
