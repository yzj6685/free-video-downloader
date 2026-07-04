from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.models import ProbeResponse, TranscriptSegment, VideoFormat
from app.services.browser_cookie_service import browser_cookie_service


class BilibiliFallbackService:
    def can_handle(self, url: str) -> bool:
        return "bilibili.com/video/" in url or "b23.tv/" in url

    def probe(self, url: str) -> ProbeResponse:
        video = self._video_data(url)
        bvid = video.get("bvid")
        aid = video.get("aid")
        cid = video.get("cid") or self._first_page_cid(video)
        if not (bvid and cid):
            raise HTTPException(status_code=502, detail="B 站页面可访问，但未找到可下载的视频分集信息。")

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
        video = self._video_data(url)
        bvid = video.get("bvid")
        aid = video.get("aid")
        cid = video.get("cid") or self._first_page_cid(video)
        if not (bvid and cid):
            raise HTTPException(status_code=502, detail="B 站页面可访问，但未找到可下载的视频分集信息。")

        quality = self._quality_from_format(format_id)
        play_info = self._playurl(str(bvid), int(cid), quality, int(aid) if aid else None)
        durl = ((play_info.get("data") or {}).get("durl") or [{}])[0]
        media_url = durl.get("url")
        if not media_url:
            raise HTTPException(status_code=502, detail="B 站低清下载地址获取失败，请稍后重试。")

        filename = self._safe_filename(video.get("title") or bvid, "mp4")
        return media_url, filename

    def subtitles(self, url: str, language: str = "zh") -> tuple[str, list[TranscriptSegment]]:
        video = self._video_data(url)
        bvid = video.get("bvid")
        aid = video.get("aid")
        cid = video.get("cid") or self._first_page_cid(video)
        if not (bvid and cid):
            raise HTTPException(status_code=502, detail="B 站页面可访问，但未找到字幕所需的视频分集信息。")

        page_track = self._pick_subtitle_track(((video.get("subtitle") or {}).get("list")) or [], language)
        track = page_track if self._track_url(page_track) else None
        if not track:
            track = self._dm_subtitle_track(str(bvid), int(cid), int(aid) if aid else None, language)
        if not track:
            track = self._subtitle_track(str(bvid), int(cid), int(aid) if aid else None, language)
        if not track:
            raise HTTPException(
                status_code=422,
                detail=(
                    "当前 B 站视频未返回可提取字幕正文。系统已尝试公开字幕接口和本机浏览器登录态；"
                    "如果网页播放器里能看到字幕，请确认 Chrome/Edge 已登录 B 站，或关闭浏览器后重试。"
                ),
            )

        subtitle_url = self._track_url(track)
        if not subtitle_url:
            raise HTTPException(
                status_code=422,
                detail=(
                    "当前 B 站视频只暴露了字幕记录，未开放字幕正文地址。"
                    "请确认浏览器已登录 B 站，或关闭 Chrome/Edge 后重试自动读取登录态。"
                ),
            )

        with httpx.Client(headers=self._headers("https://www.bilibili.com/"), timeout=30) as client:
            response = client.get(subtitle_url)
            response.raise_for_status()
            payload = response.json()

        segments = self._parse_subtitle_body(payload)
        if not segments:
            raise HTTPException(status_code=422, detail="当前 B 站视频字幕为空或无法解析，音频转写将在后续版本支持。")
        return video.get("title") or "B站视频", segments

    def stream(self, media_url: str) -> Iterator[bytes]:
        headers = self._headers("https://www.bilibili.com/")
        with httpx.stream("GET", media_url, headers=headers, follow_redirects=True, timeout=60) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(1024 * 256):
                if chunk:
                    yield chunk

    def _video_data(self, url: str) -> dict[str, Any]:
        bvid = self._bvid_from_url(url)
        if bvid:
            try:
                return self._view_data(bvid)
            except HTTPException:
                raise
            except Exception:
                pass

        state = self._initial_state(url)
        return state.get("videoData") or {}

    def _view_data(self, bvid: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"bvid": bvid})
        url = f"https://api.bilibili.com/x/web-interface/view?{query}"
        with httpx.Client(headers=self._headers(f"https://www.bilibili.com/video/{bvid}"), timeout=25) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()

        if payload.get("code") != 0:
            raise RuntimeError(payload.get("message") or "B 站视频信息接口返回失败。")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("B 站视频信息接口未返回有效数据。")
        return data

    def _bvid_from_url(self, url: str) -> str | None:
        match = re.search(r"\b(BV[0-9A-Za-z]{10})\b", url)
        return match.group(1) if match else None

    def _initial_state(self, url: str) -> dict[str, Any]:
        with httpx.Client(headers=self._headers(url), follow_redirects=True, timeout=25) as client:
            response = client.get(url)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 412:
                    raise HTTPException(
                        status_code=428,
                        detail=(
                            "平台触发了访客校验，当前无 Cookie 会话无法解析。"
                            "请配置 YTDLP_COOKIE_FILE 后重试，或更换无需 Cookie 的公开视频链接。"
                        ),
                    ) from exc
                raise
        match = re.search(r"window\.__INITIAL_STATE__=(.*?);\(function\(\)", response.text)
        if not match:
            raise HTTPException(status_code=502, detail="B 站页面结构发生变化，无法提取视频信息。")
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
            raise HTTPException(status_code=502, detail="B 站公开视频可读取，但暂时没有返回可下载 mp4 格式。")
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
            raise HTTPException(status_code=502, detail=payload.get("message") or "B 站播放地址接口返回失败。")
        return payload

    def _subtitle_track(self, bvid: str, cid: int, aid: int | None, language: str) -> dict[str, Any] | None:
        query = {"bvid": bvid, "cid": str(cid)}
        if aid:
            query["aid"] = str(aid)
        url = f"https://api.bilibili.com/x/player/v2?{urllib.parse.urlencode(query)}"
        with httpx.Client(headers=self._headers("https://www.bilibili.com/"), timeout=25) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
        if payload.get("code") != 0:
            raise HTTPException(status_code=502, detail=payload.get("message") or "B 站字幕接口返回失败。")

        subtitles = (((payload.get("data") or {}).get("subtitle") or {}).get("subtitles") or [])
        return self._pick_subtitle_track(subtitles, language)

    def _dm_subtitle_track(self, bvid: str, cid: int, aid: int | None, language: str) -> dict[str, Any] | None:
        if not aid:
            return None
        query = {"aid": str(aid), "oid": str(cid), "type": "1"}
        url = f"https://api.bilibili.com/x/v2/dm/view?{urllib.parse.urlencode(query)}"
        with httpx.Client(headers=self._headers(f"https://www.bilibili.com/video/{bvid}"), timeout=25) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
        if payload.get("code") != 0:
            return None
        subtitles = (((payload.get("data") or {}).get("subtitle") or {}).get("subtitles") or [])
        return self._pick_subtitle_track(subtitles, language)

    def _pick_subtitle_track(self, subtitles: Any, language: str) -> dict[str, Any] | None:
        if not isinstance(subtitles, list) or not subtitles:
            return None

        language_order = [language.lower(), "zh-cn", "zh-hans", "zh", "zh-tw", "en"]

        def score(item: dict[str, Any]) -> int:
            lan = str(item.get("lan") or item.get("lan_doc") or "").lower()
            try:
                return next(index for index, prefix in enumerate(language_order) if lan.startswith(prefix))
            except StopIteration:
                return len(language_order)

        candidates = [item for item in subtitles if isinstance(item, dict)]
        return sorted(candidates, key=score)[0] if candidates else None

    def _track_url(self, track: dict[str, Any] | None) -> str | None:
        if not track:
            return None
        return self._normalize_url(track.get("subtitle_url") or track.get("url"))

    def _parse_subtitle_body(self, payload: dict[str, Any]) -> list[TranscriptSegment]:
        segments: list[TranscriptSegment] = []
        for item in payload.get("body") or []:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            start = item.get("from")
            end = item.get("to")
            try:
                segments.append(TranscriptSegment(start=float(start), end=float(end) if end is not None else None, text=content))
            except (TypeError, ValueError):
                continue
        return segments

    def _first_page_cid(self, video: dict[str, Any]) -> int | None:
        pages = video.get("pages") or []
        if pages:
            return pages[0].get("cid")
        return None

    def _quality_from_format(self, format_id: str) -> int:
        match = re.search(r"(\d+)$", format_id)
        return int(match.group(1)) if match else 16

    def _headers(self, referer: str) -> dict[str, str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": referer,
        }
        cookie_header = self._cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers

    def _normalize_url(self, value: str | None) -> str | None:
        if not value:
            return None
        if value.startswith("//"):
            return f"https:{value}"
        if value.startswith("http://"):
            return f"https://{value[7:]}"
        return value.replace("\\/", "/")

    def _cookie_header(self) -> str:
        pairs: dict[str, str] = {}
        cookie_file = get_settings().cookie_file_path
        if cookie_file:
            path = Path(cookie_file)
            for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") and not line.startswith("#HttpOnly_"):
                    continue
                if line.startswith("#HttpOnly_"):
                    line = line.removeprefix("#HttpOnly_")
                parts = line.split("\t")
                if len(parts) >= 7:
                    domain, _, _, _, _, name, value = parts[:7]
                    if "bilibili.com" in domain and name and value:
                        pairs[name] = value

        browser_header = browser_cookie_service.bilibili_cookie_header(get_settings().browser_cookie_sources)
        for item in browser_header.split("; "):
            if "=" not in item:
                continue
            name, value = item.split("=", 1)
            pairs[name] = value
        return "; ".join(f"{name}={value}" for name, value in pairs.items())

    def _safe_filename(self, title: str, ext: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in title)
        return f"{cleaned[:100].strip() or 'bilibili-video'}.{ext}"


bilibili_fallback_service = BilibiliFallbackService()
