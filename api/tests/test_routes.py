from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_route_reports_runtime_state():
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "yt_dlp_available" in payload
    assert "ffmpeg_available" in payload
    assert "cookie_file_configured" in payload


def test_billing_route_returns_static_plans():
    response = client.get("/api/billing/plans")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["plans"]) >= 3
    assert any(plan["id"] == "pro" for plan in payload["plans"])


def test_ai_routes_are_explicitly_reserved():
    summary_response = client.post("/api/ai/summary")
    subtitles_response = client.post("/api/ai/translate-subtitles")

    assert summary_response.status_code == 501
    assert summary_response.json()["status"] == "coming_soon"
    assert subtitles_response.status_code == 501
    assert subtitles_response.json()["status"] == "coming_soon"


def test_probe_accepts_share_text_and_extracts_url(monkeypatch):
    async def fake_probe(url: str):
        from app.models import ProbeResponse, VideoFormat

        return ProbeResponse(
            title="demo",
            url=url,
            formats=[VideoFormat(format_id="best", label="best")],
            recommended_format_id="best",
        )

    monkeypatch.setattr("app.routers.video.ytdlp_service.probe", fake_probe)

    response = client.post(
        "/api/probe",
        json={"url": "我分享了一个视频 https://example.com/video?id=1 快来看看"},
    )

    assert response.status_code == 200
    assert response.json()["url"] == "https://example.com/video?id=1"
