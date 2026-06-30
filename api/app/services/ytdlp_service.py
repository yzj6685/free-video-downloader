from __future__ import annotations

import shutil
import subprocess
import sys
import re
from dataclasses import dataclass
from collections.abc import Iterator
from typing import Any

import httpx
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.models import ProbeResponse, VideoFormat
from app.services.bilibili_fallback import bilibili_fallback_service
from app.services.douyin_fallback import douyin_fallback_service


@dataclass(frozen=True)
class RuntimeStatus:
    yt_dlp_available: bool
    yt_dlp_version: str | None
    ffmpeg_available: bool
    cookie_file_configured: bool


class YtDlpService:
    def runtime_status(self) -> RuntimeStatus:
        try:
            import yt_dlp

            version = yt_dlp.version.__version__
            available = True
        except Exception:
            version = None
            available = False

        ffmpeg_location = get_settings().ffmpeg_location_path
        return RuntimeStatus(
            yt_dlp_available=available,
            yt_dlp_version=version,
            ffmpeg_available=ffmpeg_location is not None or shutil.which("ffmpeg") is not None,
            cookie_file_configured=get_settings().cookie_file_path is not None,
        )

    async def probe(self, url: str) -> ProbeResponse:
        try:
            info = await run_in_threadpool(self._extract_info, url)
        except HTTPException as exc:
            if bilibili_fallback_service.can_handle(url):
                return await run_in_threadpool(bilibili_fallback_service.probe, url)
            if douyin_fallback_service.can_handle(url):
                return await run_in_threadpool(douyin_fallback_service.probe, url)
            raise
        formats = self._build_formats(info)
        recommended = formats[0].format_id if formats else "best"

        return ProbeResponse(
            title=info.get("title") or "未命名视频",
            url=url,
            extractor=info.get("extractor_key") or info.get("extractor"),
            uploader=info.get("uploader") or info.get("channel"),
            duration=info.get("duration"),
            thumbnail=info.get("thumbnail"),
            formats=formats or [
                VideoFormat(
                    format_id="best",
                    label="最佳可用格式",
                    extension=info.get("ext"),
                    resolution=info.get("resolution"),
                )
            ],
            recommended_format_id=recommended,
            may_require_proxy=self._may_require_proxy(info),
        )

    async def get_direct_url(self, url: str, format_id: str) -> tuple[str, str]:
        if format_id.startswith("bili-html5-"):
            return await run_in_threadpool(bilibili_fallback_service.direct_url, url, format_id)
        if format_id.startswith("douyin-resolver-"):
            response = await run_in_threadpool(douyin_fallback_service.direct_url, url, format_id)
            return response.url, response.filename

        info = await run_in_threadpool(self._extract_info, url, format_id)
        direct_url = info.get("url")
        if not direct_url and info.get("requested_downloads"):
            first_download = info["requested_downloads"][0]
            direct_url = first_download.get("url")

        if not direct_url:
            raise HTTPException(
                status_code=502,
                detail="该链接暂时无法生成直连下载地址，请稍后重试或更换格式。",
            )

        filename = self._safe_filename(info)
        return direct_url, filename

    async def get_filename(self, url: str, format_id: str) -> str:
        if format_id.startswith("bili-html5-"):
            _, filename = await run_in_threadpool(bilibili_fallback_service.direct_url, url, format_id)
            return filename
        if format_id.startswith("douyin-resolver-"):
            response = await run_in_threadpool(douyin_fallback_service.direct_url, url, format_id)
            return response.filename

        info = await run_in_threadpool(self._extract_info, url, format_id)
        return self._safe_filename(info)

    def stream_download(self, url: str, format_id: str) -> Iterator[bytes]:
        if format_id.startswith("bili-html5-"):
            media_url, _ = bilibili_fallback_service.direct_url(url, format_id)
            yield from bilibili_fallback_service.stream(media_url)
            return
        if format_id.startswith("douyin-resolver-"):
            response = douyin_fallback_service.direct_url(url, format_id)
            yield from self._stream_remote(response.url, self._headers_for(url))
            return

        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "--user-agent",
            self._user_agent(),
            "--add-header",
            "Accept-Language:zh-CN,zh;q=0.9,en;q=0.8",
            "-f",
            format_id,
            "-o",
            "-",
            url,
        ]
        cookie_file = get_settings().cookie_file_path
        if cookie_file:
            command[3:3] = ["--cookies", cookie_file]
        ffmpeg_location = get_settings().ffmpeg_location_path
        if ffmpeg_location:
            command[3:3] = ["--ffmpeg-location", ffmpeg_location]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            assert process.stdout is not None
            while True:
                chunk = process.stdout.read(1024 * 256)
                if not chunk:
                    break
                yield chunk

            return_code = process.wait(timeout=5)
            if return_code != 0:
                stderr = process.stderr.read().decode("utf-8", errors="ignore") if process.stderr else ""
                raise RuntimeError(stderr or "yt-dlp 下载中转失败")
        finally:
            if process.poll() is None:
                process.kill()

    def stream_thumbnail(self, url: str, source_url: str | None = None) -> tuple[str, Iterator[bytes]]:
        headers = self._headers_for(source_url or url)

        def iterator() -> Iterator[bytes]:
            yield from self._stream_remote(url, headers)

        return self._guess_media_type(url), iterator()

    def stream_remote_range(
        self,
        media_url: str,
        source_url: str,
        range_header: str | None,
        default_limit: int = 1024 * 1024,
    ) -> tuple[int, dict[str, str], Iterator[bytes]]:
        headers = self._headers_for(source_url)
        total = self._remote_content_length(media_url, headers)
        start, end = self._parse_range_header(range_header, total, default_limit)
        request_headers = {**headers, "Range": f"bytes={start}-{end}"}
        length = end - start + 1

        response_headers = {
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=120",
            "Content-Length": str(length),
        }
        if total is not None:
            response_headers["Content-Range"] = f"bytes {start}-{end}/{total}"

        def iterator() -> Iterator[bytes]:
            yield from self._stream_remote(media_url, request_headers)

        return 206, response_headers, iterator()

    def _extract_info(self, url: str, format_id: str | None = None) -> dict[str, Any]:
        try:
            import yt_dlp
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="当前环境未安装 yt-dlp，请先安装后再解析视频。",
            ) from exc

        options: dict[str, Any] = {
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
            "no_warnings": True,
            "socket_timeout": 25,
            "retries": 2,
            "fragment_retries": 2,
            "http_headers": self._headers_for(url),
        }
        cookie_file = get_settings().cookie_file_path
        if cookie_file:
            options["cookiefile"] = cookie_file
        ffmpeg_location = get_settings().ffmpeg_location_path
        if ffmpeg_location:
            options["ffmpeg_location"] = ffmpeg_location
        if format_id:
            options["format"] = format_id

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(url, download=False)
        except HTTPException:
            raise
        except Exception as exc:
            raise self._map_error(exc) from exc

    def _build_formats(self, info: dict[str, Any]) -> list[VideoFormat]:
        raw_formats = info.get("formats") or []
        usable: list[VideoFormat] = []

        for item in raw_formats:
            format_id = str(item.get("format_id") or "")
            if not format_id:
                continue

            vcodec = item.get("vcodec")
            acodec = item.get("acodec")
            has_video = bool(vcodec and vcodec != "none")
            has_audio = bool(acodec and acodec != "none")
            if not has_video and not has_audio:
                continue

            height = item.get("height")
            resolution = item.get("resolution") or (f"{height}p" if height else None)
            ext = item.get("ext")
            note = item.get("format_note")
            label_parts = [part for part in [resolution, note, ext] if part]
            label = " / ".join(label_parts) or item.get("format") or format_id

            usable.append(
                VideoFormat(
                    format_id=format_id,
                    label=label,
                    extension=ext,
                    resolution=resolution,
                    filesize=item.get("filesize") or item.get("filesize_approx"),
                    has_video=has_video,
                    has_audio=has_audio,
                )
            )

        usable.sort(key=self._format_sort_key, reverse=True)
        return usable[:16]

    def _format_sort_key(self, item: VideoFormat) -> tuple[int, int, int]:
        height = 0
        if item.resolution and item.resolution.endswith("p"):
            try:
                height = int(item.resolution[:-1])
            except ValueError:
                height = 0
        return (1 if item.has_video and item.has_audio else 0, height, item.filesize or 0)

    def _may_require_proxy(self, info: dict[str, Any]) -> bool:
        requested = info.get("requested_formats")
        return bool(requested) or not bool(info.get("url"))

    def _safe_filename(self, info: dict[str, Any]) -> str:
        title = info.get("title") or "video"
        ext = info.get("ext") or "mp4"
        cleaned = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in title)
        return f"{cleaned[:100].strip() or 'video'}.{ext}"

    def _headers_for(self, url: str) -> dict[str, str]:
        headers = {
            "User-Agent": self._user_agent(),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if "bilibili.com" in url or "hdslb.com" in url:
            headers["Referer"] = "https://www.bilibili.com/"
        elif "douyin.com" in url or "douyinvod.com" in url or "douyinpic.com" in url or "byteimg.com" in url:
            headers["Referer"] = "https://www.douyin.com/"
        return headers

    def _stream_remote(self, url: str, headers: dict[str, str]) -> Iterator[bytes]:
        with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=60) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(1024 * 256):
                if chunk:
                    yield chunk

    def _remote_content_length(self, url: str, headers: dict[str, str]) -> int | None:
        try:
            with httpx.Client(headers=headers, follow_redirects=True, timeout=20) as client:
                response = client.head(url)
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length and length.isdigit():
                    return int(length)
        except Exception:
            return None
        return None

    def _parse_range_header(
        self,
        range_header: str | None,
        total: int | None,
        default_limit: int,
    ) -> tuple[int, int]:
        start = 0
        end = default_limit - 1
        if range_header:
            match = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
            if match:
                raw_start, raw_end = match.groups()
                if raw_start:
                    start = int(raw_start)
                if raw_end:
                    end = int(raw_end)
                else:
                    end = start + default_limit - 1
        if total is not None:
            end = min(end, total - 1)
        end = max(start, end)
        return start, end

    def _guess_media_type(self, url: str) -> str:
        lowered = url.lower().split("?", 1)[0]
        if lowered.endswith(".png"):
            return "image/png"
        if lowered.endswith(".webp"):
            return "image/webp"
        if lowered.endswith(".gif"):
            return "image/gif"
        return "image/jpeg"

    def _user_agent(self) -> str:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

    def _map_error(self, exc: Exception) -> HTTPException:
        message = str(exc)
        lowered = message.lower()
        if "fresh cookies" in lowered or "cookies are needed" in lowered:
            detail = (
                "该平台要求新鲜 Cookie 才能解析。请在本地配置 YTDLP_COOKIE_FILE 指向你主动导出的 cookies.txt，"
                "然后重启后端再试。"
            )
            status = 428
        elif "http error 412" in lowered or "precondition failed" in lowered:
            detail = (
                "平台触发了访客校验，当前无 Cookie 会话无法解析。请配置 YTDLP_COOKIE_FILE 后重试，"
                "或更换无需 Cookie 的公开视频链接。"
            )
            status = 428
        elif "unsupported url" in lowered or "not a valid url" in lowered:
            detail = "请输入正确的视频链接。"
            status = 400
        elif "private" in lowered or "login" in lowered or "sign in" in lowered:
            detail = "该内容可能需要登录或权限，当前演示版暂不支持。"
            status = 403
        elif "copyright" in lowered or "drm" in lowered:
            detail = "该内容受平台或版权限制，当前演示版不支持下载。"
            status = 403
        else:
            detail = "平台限制或链接已失效，建议更换链接重试。"
            status = 502
        return HTTPException(status_code=status, detail=detail)


ytdlp_service = YtDlpService()
