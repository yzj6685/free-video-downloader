from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Iterator
from typing import Any

import httpx
from fastapi import HTTPException

from app.models import ProbeResponse, VideoFormat


class BilibiliFallbackService:
    def can_handle(self, url: str) -> bool:
        return "bilibili.com/video/" in url or "b23.tv/" in url

    def probe(self, url: str) -> ProbeResponse:
        state = self._initial_state(url)
        video = state.get("videoData") or {}
        bvid = video.get("bvid")
        aid = video.get("aid")
        cid = video.get("cid") or self._first_page_cid(video)
        if not (bvid and cid):
            raise HTTPException(status_code=502, detail="B站页面可访问，但未找到可下载的视频分集信息。")

        formats = self._play_formats(str(bvid), int(cid), int(aid) if aid else None)
        title = video.get("title") or "B站视频"
        return ProbeResponse(
            title=title,
            url=url,
            extractor="BiliBiliFallback",
            uploader=(video.get("owner") or {}).get("name"),
            duration=video.get("duration"),
            thumbnail=self._normalize_url(video.get("pic")),
            formats=formats,
            recommended_format_id=formats[0].format_id,
            may_require_proxy=True,
        )

    def direct_url(self, url: str, format_id: str) -> tuple[str, str]:
        state = self._initial_state(url)
        video = state.get("videoData") or {}
        bvid = video.get("bvid")
        aid = video.get("aid")
        cid = video.get("cid") or self._first_page_cid(video)
        if not (bvid and cid):
            raise HTTPException(status_code=502, detail="B站页面可访问，但未找到可下载的视频分集信息。")

        quality = self._quality_from_format(format_id)
        play_info = self._playurl(str(bvid), int(cid), quality, int(aid) if aid else None)
        durl = ((play_info.get("data") or {}).get("durl") or [{}])[0]
        media_url = durl.get("url")
        if not media_url:
            raise HTTPException(status_code=502, detail="B站低清下载地址获取失败，请稍后重试。")

        filename = self._safe_filename(video.get("title") or bvid, "mp4")
        return media_url, filename

    def stream(self, media_url: str) -> Iterator[bytes]:
        headers = self._headers("https://www.bilibili.com/")
        with httpx.stream("GET", media_url, headers=headers, follow_redirects=True, timeout=60) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(1024 * 256):
                if chunk:
                    yield chunk

    def _initial_state(self, url: str) -> dict[str, Any]:
        with httpx.Client(headers=self._headers(url), follow_redirects=True, timeout=25) as client:
            response = client.get(url)
            response.raise_for_status()
        match = re.search(r"window\.__INITIAL_STATE__=(.*?);\(function\(\)", response.text)
        if not match:
            raise HTTPException(status_code=502, detail="B站页面结构发生变化，无法提取视频信息。")
        return json.loads(match.group(1))

    def _play_formats(self, bvid: str, cid: int, aid: int | None) -> list[VideoFormat]:
        qualities = [16, 80]
        labels = {16: "流畅 360P mp4", 80: "高清 1080P mp4"}
        formats: list[VideoFormat] = []
        for quality in qualities:
            play_info = self._playurl(bvid, cid, quality, aid)
            data = play_info.get("data") or {}
            durl = data.get("durl") or []
            if not durl:
                continue
            formats.append(
                VideoFormat(
                    format_id=f"bili-html5-{quality}",
                    label=labels.get(quality, f"B站 mp4 qn={quality}"),
                    extension="mp4",
                    resolution="360p" if quality == 16 else "1080p",
                    filesize=durl[0].get("size"),
                    has_video=True,
                    has_audio=True,
                )
            )
        if not formats:
            raise HTTPException(status_code=502, detail="B站公开视频可读取，但暂时没有返回可下载 mp4 格式。")
        return formats

    def _playurl(self, bvid: str, cid: int, quality: int, aid: int | None) -> dict[str, Any]:
        query = {
            "bvid": bvid,
            "cid": str(cid),
            "qn": str(quality),
            "type": "",
            "otype": "json",
            "platform": "html5",
            "high_quality": "0",
        }
        if aid:
            query["avid"] = str(aid)
        url = f"https://api.bilibili.com/x/player/playurl?{urllib.parse.urlencode(query)}"
        with httpx.Client(headers=self._headers("https://www.bilibili.com/"), timeout=25) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
        if payload.get("code") != 0:
            raise HTTPException(status_code=502, detail=payload.get("message") or "B站播放地址接口返回失败。")
        return payload

    def _first_page_cid(self, video: dict[str, Any]) -> int | None:
        pages = video.get("pages") or []
        if pages:
            return pages[0].get("cid")
        return None

    def _quality_from_format(self, format_id: str) -> int:
        match = re.search(r"(\d+)$", format_id)
        return int(match.group(1)) if match else 16

    def _headers(self, referer: str) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": referer,
        }

    def _normalize_url(self, value: str | None) -> str | None:
        if not value:
            return None
        if value.startswith("//"):
            return f"https:{value}"
        return value.replace("\\/", "/")

    def _safe_filename(self, title: str, ext: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in title)
        return f"{cleaned[:100].strip() or 'bilibili-video'}.{ext}"


bilibili_fallback_service = BilibiliFallbackService()
