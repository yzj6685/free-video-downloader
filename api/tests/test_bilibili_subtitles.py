from fastapi import HTTPException

from app.services.bilibili_fallback import BilibiliFallbackService
from app.services.browser_cookie_service import BrowserCookieService


def test_bilibili_picks_page_subtitle_url():
    service = BilibiliFallbackService()
    track = service._pick_subtitle_track(
        [
            {"lan": "en", "subtitle_url": "//example.com/en.json"},
            {"lan": "zh", "subtitle_url": "//example.com/zh.json"},
        ],
        "zh",
    )

    assert service._track_url(track) == "https://example.com/zh.json"


def test_bilibili_empty_page_subtitle_url_needs_login_state(monkeypatch):
    service = BilibiliFallbackService()
    monkeypatch.setattr(
        service,
        "_initial_state",
        lambda url: {
            "videoData": {
                "bvid": "BVtest",
                "aid": 1,
                "cid": 2,
                "title": "B站测试视频",
                "subtitle": {"list": [{"lan": "zh", "subtitle_url": ""}]},
            }
        },
    )
    monkeypatch.setattr(service, "_subtitle_track", lambda bvid, cid, aid, language: None)

    try:
        service.subtitles("https://bilibili.com/video/BVtest")
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "浏览器登录态" in exc.detail
    else:
        raise AssertionError("Expected Bilibili subtitle login-state error")


def test_bilibili_uses_dm_subtitle_track(monkeypatch):
    service = BilibiliFallbackService()
    monkeypatch.setattr(
        service,
        "_initial_state",
        lambda url: {
            "videoData": {
                "bvid": "BVtest",
                "aid": 1,
                "cid": 2,
                "title": "B站测试视频",
                "subtitle": {"list": [{"lan": "zh", "subtitle_url": ""}]},
            }
        },
    )
    monkeypatch.setattr(
        service,
        "_dm_subtitle_track",
        lambda bvid, cid, aid, language: {"lan": "zh", "subtitle_url": "//example.com/subtitle.json"},
    )
    monkeypatch.setattr(service, "_parse_subtitle_body", lambda payload: [])

    assert service._track_url(service._dm_subtitle_track("BVtest", 2, 1, "zh")) == "https://example.com/subtitle.json"


def test_browser_cookie_service_builds_bilibili_cookie_header(monkeypatch):
    class Cookie:
        domain = ".bilibili.com"
        name = "SESSDATA"
        value = "token"

    service = BrowserCookieService()
    monkeypatch.setattr(service, "_load_browser", lambda browser: [Cookie()])

    assert service.bilibili_cookie_header(["chrome"]) == "SESSDATA=token"
