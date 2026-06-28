from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.models import DirectDownloadResponse, ProbeResponse, VideoFormat


PUBLIC_RESOLVER_ENDPOINTS = [
    "https://api.mmp.cc/api/Jiexi",
]


class DouyinFallbackService:
    def can_handle(self, url: str) -> bool:
        return any(host in url for host in ("douyin.com", "iesdouyin.com"))

    def probe(self, url: str) -> ProbeResponse:
        resolved_url, aweme_id = self._resolve_url_and_id(url)
        payload = self._call_resolvers(resolved_url, aweme_id)
        return self._normalize_probe(url, payload, aweme_id)

    def direct_url(self, url: str, format_id: str) -> DirectDownloadResponse:
        resolved_url, aweme_id = self._resolve_url_and_id(url)
        payload = self._call_resolvers(resolved_url, aweme_id)
        media_url = self._pick_media_url(payload, format_id)
        title = self._pick_title(payload) or f"douyin-{aweme_id}"
        if not media_url:
            raise HTTPException(status_code=502, detail="抖音解析源没有返回可下载的视频地址。")
        return DirectDownloadResponse(type="direct", url=media_url, filename=self._safe_filename(title, "mp4"))

    def _resolve_url_and_id(self, url: str) -> tuple[str, str]:
        resolved_url = url
        if "v.douyin.com" in url:
            with httpx.Client(headers=self._headers(), follow_redirects=False, timeout=20) as client:
                response = client.get(url)
            location = response.headers.get("location")
            if location:
                resolved_url = location

        for pattern in (r"/video/(\d+)", r"modal_id=(\d+)", r"aweme_id=(\d+)"):
            match = re.search(pattern, resolved_url)
            if match:
                return resolved_url, match.group(1)

        raise HTTPException(status_code=400, detail="无法从抖音链接中识别视频 ID。")

    def _call_resolvers(self, resolved_url: str, aweme_id: str) -> dict[str, Any]:
        errors: list[str] = []
        for endpoint in self._resolver_endpoints():
            try:
                payload = self._call_resolver(endpoint, resolved_url, aweme_id)
            except Exception as exc:
                errors.append(f"{endpoint}: {exc}")
                continue

            if not self._is_success_payload(payload):
                errors.append(f"{endpoint}: {payload.get('msg') or payload.get('message') or '解析失败'}")
                continue
            if self._is_non_video_payload(payload):
                raise HTTPException(status_code=422, detail="该抖音链接被识别为图集或非视频内容，首版只支持视频下载。")
            if self._pick_media_url(payload):
                return payload
            errors.append(f"{endpoint}: 解析成功但没有返回视频下载地址")

        detail = (
            "抖音公开视频需要服务端签名解析。当前默认解析源未返回可下载地址，"
            "可以配置 DOUYIN_RESOLVER_ENDPOINT 接入自建或商业解析服务后重试。"
        )
        if errors:
            detail = f"{detail} 最近一次解析信息：{errors[-1]}"
        raise HTTPException(status_code=502, detail=detail)

    def _resolver_endpoints(self) -> list[str]:
        configured = get_settings().douyin_resolver_endpoint
        endpoints = [item.strip() for item in configured.split(",") if item.strip()]
        return endpoints or PUBLIC_RESOLVER_ENDPOINTS

    def _call_resolver(self, endpoint: str, resolved_url: str, aweme_id: str) -> dict[str, Any]:
        with httpx.Client(headers=self._headers(), timeout=45) as client:
            response = client.get(endpoint, params={"url": resolved_url, "aweme_id": aweme_id})
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("解析源返回了非 JSON 对象")
        return payload

    def _normalize_probe(self, original_url: str, payload: dict[str, Any], aweme_id: str) -> ProbeResponse:
        title = self._pick_title(payload) or f"抖音视频 {aweme_id}"
        if not self._pick_media_url(payload):
            raise HTTPException(status_code=502, detail="抖音解析源没有返回可下载的视频地址。")
        formats = self._build_formats(payload)

        return ProbeResponse(
            title=title,
            url=original_url,
            extractor="DouyinResolver",
            uploader=self._pick_author(payload),
            duration=self._pick_duration(payload),
            thumbnail=self._pick_cover(payload),
            formats=formats,
            recommended_format_id=formats[0].format_id,
            may_require_proxy=True,
        )

    def _build_formats(self, payload: dict[str, Any]) -> list[VideoFormat]:
        formats: list[VideoFormat] = []
        for format_id, label, media_url in self._media_candidates(payload):
            formats.append(
                VideoFormat(
                    format_id=format_id,
                    label=label,
                    extension="mp4",
                    resolution=None,
                    filesize=self._probe_filesize(media_url),
                    has_video=True,
                    has_audio=True,
                )
            )
        if not formats:
            raise HTTPException(status_code=502, detail="抖音解析源没有返回可下载的视频地址。")
        return formats

    def _media_candidates(self, payload: dict[str, Any]) -> list[tuple[str, str, str]]:
        raw_candidates = [
            ("douyin-resolver-cdn", "抖音高清源 mp4", self._pick_nested(payload, ["video", "cdn_url"])),
            ("douyin-resolver-play", "抖音播放源 mp4", self._pick_nested(payload, ["video", "video_url"])),
            ("douyin-resolver-download", "抖音下载源 mp4", payload.get("download_url")),
            ("douyin-resolver-url", "抖音备用源 mp4", payload.get("url")),
            ("douyin-resolver-play-url", "抖音备用播放源 mp4", payload.get("play_url")),
            ("douyin-resolver-nested", "抖音嵌套播放源 mp4", self._pick_nested(payload, ["video", "play_addr", "url_list", 0])),
            ("douyin-resolver-aweme", "抖音作品播放源 mp4", self._pick_nested(payload, ["aweme_detail", "video", "play_addr", "url_list", 0])),
            ("douyin-resolver-data-video", "抖音数据源 mp4", self._pick_nested(payload, ["data", "video_url"])),
            ("douyin-resolver-data-download", "抖音数据下载源 mp4", self._pick_nested(payload, ["data", "download_url"])),
        ]
        seen: set[str] = set()
        candidates: list[tuple[str, str, str]] = []
        for format_id, label, media_url in raw_candidates:
            if not isinstance(media_url, str) or not media_url.startswith("http"):
                continue
            if media_url in seen:
                continue
            seen.add(media_url)
            candidates.append((format_id, label, media_url))
        return candidates

    def _pick_media_url(self, payload: dict[str, Any], format_id: str | None = None) -> str | None:
        candidates = self._media_candidates(payload)
        if format_id:
            for candidate_id, _label, media_url in candidates:
                if candidate_id == format_id:
                    return media_url
        if candidates:
            return candidates[0][2]

        fallback = payload.get("video_url") or self._pick_nested(payload, ["data", "url"])
        return fallback if isinstance(fallback, str) and fallback.startswith("http") else None

    def _probe_filesize(self, media_url: str) -> int | None:
        try:
            with httpx.Client(headers=self._headers(), follow_redirects=True, timeout=20) as client:
                response = client.head(media_url)
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length and length.isdigit():
                    return int(length)
        except Exception:
            return None
        return None

    def _is_success_payload(self, payload: dict[str, Any]) -> bool:
        code = payload.get("code")
        status = payload.get("status")
        return code in (0, 1, 200, "0", "1", "200") or status in ("success", "ok", True)

    def _is_non_video_payload(self, payload: dict[str, Any]) -> bool:
        payload_type = str(payload.get("type") or payload.get("media_type") or "").lower()
        return any(marker in payload_type for marker in ("图集", "image", "photo", "note"))

    def _pick_title(self, payload: dict[str, Any]) -> str | None:
        return (
            payload.get("title")
            or payload.get("desc")
            or self._pick_nested(payload, ["aweme_detail", "desc"])
            or self._pick_nested(payload, ["data", "title"])
            or self._pick_nested(payload, ["data", "desc"])
        )

    def _pick_author(self, payload: dict[str, Any]) -> str | None:
        author = payload.get("author")
        if isinstance(author, str):
            return author
        return (
            self._pick_nested(payload, ["author", "nickname"])
            or payload.get("author_name")
            or self._pick_nested(payload, ["aweme_detail", "author", "nickname"])
        )

    def _pick_duration(self, payload: dict[str, Any]) -> int | None:
        value = payload.get("duration") or self._pick_nested(payload, ["video", "duration"])
        if isinstance(value, int):
            return value // 1000 if value > 10000 else value
        return None

    def _pick_cover(self, payload: dict[str, Any]) -> str | None:
        return (
            payload.get("cover")
            or payload.get("cover_url")
            or self._pick_nested(payload, ["video", "cover"])
            or self._pick_nested(payload, ["video", "cover", "url_list", 0])
            or self._pick_nested(payload, ["aweme_detail", "video", "cover", "url_list", 0])
        )

    def _pick_nested(self, payload: Any, path: list[str | int]) -> Any:
        value = payload
        for key in path:
            if isinstance(key, int) and isinstance(value, list) and len(value) > key:
                value = value[key]
            elif isinstance(key, str) and isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.douyin.com/",
        }

    def _safe_filename(self, title: str, ext: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in title)
        return f"{cleaned[:100].strip() or 'douyin-video'}.{ext}"


douyin_fallback_service = DouyinFallbackService()
