from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.models import DirectDownloadResponse, ProbeResponse, TranscriptSegment, VideoFormat


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

    def metadata_transcript(self, url: str) -> tuple[str, list[TranscriptSegment]]:
        resolved_url, aweme_id = self._resolve_url_and_id(url)
        payload = self._call_resolvers(resolved_url, aweme_id)
        title = self._pick_title(payload) or f"抖音视频 {aweme_id}"
        segments = self._metadata_segments(payload, title)
        if not segments:
            raise HTTPException(
                status_code=422,
                detail="当前抖音视频未返回可用于总结的公开文案，音频转写将在后续版本支持。",
            )
        return title, segments

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
                errors.append(f"{endpoint}: {payload.get('msg') or payload.get('message') or 'parse failed'}")
                continue
            if self._is_non_video_payload(payload):
                raise HTTPException(status_code=422, detail="该抖音链接被识别为图集或非视频内容，当前只支持视频下载。")
            if self._pick_media_url(payload):
                return payload
            errors.append(f"{endpoint}: parsed successfully but did not include a video URL")

        try:
            payload = self._call_share_page(resolved_url, aweme_id)
        except Exception as exc:
            errors.append(f"share-page: {exc}")
        else:
            if self._is_non_video_payload(payload):
                raise HTTPException(status_code=422, detail="该抖音链接被识别为图集或非视频内容，当前只支持视频下载。")
            if self._pick_media_url(payload):
                return payload
            errors.append("share-page: parsed successfully but did not include a video URL")

        detail = (
            "抖音公开视频需要服务端签名解析。当前默认解析源未返回可下载地址，"
            "也未能从分享页读取视频地址，可以配置 DOUYIN_RESOLVER_ENDPOINT 接入自建或商业解析服务后重试。"
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

    def _call_share_page(self, resolved_url: str, aweme_id: str) -> dict[str, Any]:
        share_url = self._share_page_url(resolved_url, aweme_id)
        with httpx.Client(headers=self._mobile_headers(), follow_redirects=True, timeout=30) as client:
            response = client.get(share_url)
            response.raise_for_status()
            html = response.text or ""
        router_data = self._extract_router_data(html)
        item = self._extract_item_from_router_data(router_data)
        if not item:
            raise ValueError("share page did not include video metadata")
        return {
            "code": 200,
            "type": "视频",
            "desc": item.get("desc"),
            "author": item.get("author"),
            "video": item.get("video"),
            "aweme_detail": item,
        }

    def _share_page_url(self, resolved_url: str, aweme_id: str) -> str:
        parsed = urlparse(resolved_url)
        if "iesdouyin.com" in parsed.netloc and f"/{aweme_id}" in parsed.path:
            return resolved_url
        return f"https://www.iesdouyin.com/share/video/{aweme_id}/"

    def _extract_router_data(self, html: str) -> dict[str, Any]:
        marker = "window._ROUTER_DATA = "
        start = html.find(marker)
        if start < 0:
            return {}

        index = start + len(marker)
        while index < len(html) and html[index].isspace():
            index += 1
        if index >= len(html) or html[index] != "{":
            return {}

        depth = 0
        in_string = False
        escaped = False
        for cursor in range(index, len(html)):
            char = html[cursor]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        payload = json.loads(html[index : cursor + 1])
                    except ValueError:
                        return {}
                    return payload if isinstance(payload, dict) else {}
        return {}

    def _extract_item_from_router_data(self, router_data: dict[str, Any]) -> dict[str, Any]:
        loader_data = router_data.get("loaderData")
        if not isinstance(loader_data, dict):
            return {}
        for node in loader_data.values():
            if not isinstance(node, dict):
                continue
            video_info = node.get("videoInfoRes")
            if not isinstance(video_info, dict):
                continue
            item_list = video_info.get("item_list")
            if isinstance(item_list, list) and item_list and isinstance(item_list[0], dict):
                return item_list[0]
        return {}

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
            (
                "douyin-resolver-aweme",
                "抖音作品播放源 mp4",
                self._pick_nested(payload, ["aweme_detail", "video", "play_addr", "url_list", 0]),
            ),
            ("douyin-resolver-data-video", "抖音数据源 mp4", self._pick_nested(payload, ["data", "video_url"])),
            ("douyin-resolver-data-download", "抖音数据下载源 mp4", self._pick_nested(payload, ["data", "download_url"])),
        ]
        for index, item in enumerate(self._pick_nested(payload, ["video", "bit_rate"]) or []):
            if not isinstance(item, dict):
                continue
            media_url = self._pick_nested(item, ["play_addr", "url_list", 0])
            height = item.get("height")
            width = item.get("width")
            label = "抖音清晰源 mp4"
            if width and height:
                label = f"抖音清晰源 {width}x{height} mp4"
            elif height:
                label = f"抖音清晰源 {height}p mp4"
            raw_candidates.append((f"douyin-resolver-bitrate-{index}", label, media_url))

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
        value = (
            payload.get("duration")
            or self._pick_nested(payload, ["video", "duration"])
            or self._pick_nested(payload, ["aweme_detail", "video", "duration"])
        )
        if isinstance(value, int):
            return value // 1000 if value > 10000 else value
        return None

    def _pick_cover(self, payload: dict[str, Any]) -> str | None:
        cover = (
            payload.get("cover")
            or payload.get("cover_url")
            or self._pick_nested(payload, ["video", "cover", "url_list", 0])
            or self._pick_nested(payload, ["video", "origin_cover", "url_list", 0])
            or self._pick_nested(payload, ["video", "dynamic_cover", "url_list", 0])
            or self._pick_nested(payload, ["aweme_detail", "video", "cover", "url_list", 0])
        )
        return cover if isinstance(cover, str) and cover.startswith("http") else None

    def _metadata_segments(self, payload: dict[str, Any], title: str) -> list[TranscriptSegment]:
        candidates = [
            title,
            payload.get("desc"),
            payload.get("title"),
            self._pick_nested(payload, ["aweme_detail", "desc"]),
            self._pick_nested(payload, ["data", "desc"]),
            self._pick_nested(payload, ["data", "title"]),
        ]
        texts: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            text = self._clean_metadata_text(candidate)
            if not text or text in seen or re.fullmatch(r"抖音视频\s+\d+", text):
                continue
            seen.add(text)
            texts.append(text)
        return [TranscriptSegment(start=float(index), end=None, text=text) for index, text in enumerate(texts)]

    def _clean_metadata_text(self, value: str) -> str:
        text = re.sub(r"https?://\S+", "", value)
        text = re.sub(r"\s+", " ", text).strip(" \t\r\n，。；;")
        return text

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

    def _mobile_headers(self) -> dict[str, str]:
        headers = self._headers()
        headers["User-Agent"] = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
            "Mobile/15E148 Safari/604.1"
        )
        return headers

    def _safe_filename(self, title: str, ext: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in title)
        return f"{cleaned[:100].strip() or 'douyin-video'}.{ext}"


douyin_fallback_service = DouyinFallbackService()
