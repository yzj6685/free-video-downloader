from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from urllib.parse import quote, urlencode

from app.models import (
    CapabilitiesResponse,
    DirectDownloadResponse,
    DownloadRequest,
    HealthResponse,
    ProbeRequest,
    ProbeResponse,
)
from app.services.capabilities_service import get_capabilities
from app.services.ytdlp_service import ytdlp_service

router = APIRouter(prefix="/api", tags=["video"])


def attachment_headers(filename: str) -> dict[str, str]:
    fallback = "".join(ch if ch.isascii() and ch.isalnum() or ch in "._-" else "_" for ch in filename)
    fallback = fallback or "video.mp4"
    encoded = quote(filename, safe="")
    return {"Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"}


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    status = ytdlp_service.runtime_status()
    message = "服务正常"
    if not status.yt_dlp_available:
        message = "API 可用，但当前环境未安装 yt-dlp"
    elif not status.ffmpeg_available:
        message = "API 和 yt-dlp 可用；未检测到 ffmpeg，部分高清合并格式可能不可用"

    return HealthResponse(
        status="ok",
        yt_dlp_available=status.yt_dlp_available,
        yt_dlp_version=status.yt_dlp_version,
        ffmpeg_available=status.ffmpeg_available,
        cookie_file_configured=status.cookie_file_configured,
        message=message,
    )


@router.get("/capabilities", response_model=CapabilitiesResponse)
def capabilities() -> CapabilitiesResponse:
    return get_capabilities()


@router.post("/probe", response_model=ProbeResponse)
async def probe(payload: ProbeRequest) -> ProbeResponse:
    return await ytdlp_service.probe(str(payload.url))


@router.post("/download")
async def download(payload: DownloadRequest):
    if payload.delivery == "proxy":
        filename = await ytdlp_service.get_filename(str(payload.url), payload.format_id)
        return StreamingResponse(
            ytdlp_service.stream_download(str(payload.url), payload.format_id),
            media_type="application/octet-stream",
            headers=attachment_headers(filename),
        )

    direct_url, filename = await ytdlp_service.get_direct_url(
        str(payload.url), payload.format_id
    )
    if payload.format_id.startswith("bili-html5-"):
        query = urlencode({"url": str(payload.url), "format_id": payload.format_id})
        return DirectDownloadResponse(
            type="proxy",
            url=f"/api/download/file?{query}",
            filename=filename,
        )
    if payload.format_id.startswith("douyin-resolver-"):
        query = urlencode({"url": str(payload.url), "format_id": payload.format_id})
        return DirectDownloadResponse(
            type="proxy",
            url=f"/api/download/file?{query}",
            filename=filename,
        )
    if payload.delivery == "direct":
        return DirectDownloadResponse(type="direct", url=direct_url, filename=filename)

    # auto/proxy both use a redirect-first handoff. A true proxy stream can be
    # added if hosted infrastructure needs stricter bandwidth control.
    return RedirectResponse(url=direct_url, headers={"X-Suggested-Filename": filename})


@router.get("/download/file")
async def download_file(url: str, format_id: str = "best"):
    filename = await ytdlp_service.get_filename(url, format_id)
    return StreamingResponse(
        ytdlp_service.stream_download(url, format_id),
        media_type="application/octet-stream",
        headers=attachment_headers(filename),
    )


@router.get("/media/thumbnail")
def thumbnail(url: str, source_url: str | None = None):
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="请输入正确的封面图片地址。")

    media_type, stream = ytdlp_service.stream_thumbnail(url, source_url)
    return StreamingResponse(
        stream,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/media/video-preview")
async def video_preview(url: str, format_id: str, request: Request):
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="请输入正确的视频链接。")

    media_url, _filename = await ytdlp_service.get_direct_url(url, format_id)
    status_code, headers, stream = ytdlp_service.stream_remote_range(
        media_url,
        url,
        request.headers.get("range"),
    )
    return StreamingResponse(
        stream,
        status_code=status_code,
        media_type="video/mp4",
        headers=headers,
    )
