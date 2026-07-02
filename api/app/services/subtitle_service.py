from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.models import TranscriptSegment
from app.services.asr_service import asr_service
from app.services.bilibili_fallback import bilibili_fallback_service
from app.services.douyin_fallback import douyin_fallback_service


@dataclass(frozen=True)
class SubtitleTrack:
    language: str
    url: str
    ext: str
    automatic: bool = False


class SubtitleService:
    async def extract(self, url: str, language: str = "zh", format_id: str = "best") -> tuple[str, list[TranscriptSegment]]:
        if self._should_use_douyin_fallback(url, format_id):
            return await self._extract_douyin(url, format_id)

        try:
            info = await run_in_threadpool(self._extract_info, url)
        except HTTPException as exc:
            if self._should_use_douyin_fallback(url, format_id):
                return await self._extract_douyin(url, format_id)
            if get_settings().browser_cookie_sources:
                try:
                    info = await run_in_threadpool(self._extract_info_with_browser_cookies, url)
                except HTTPException:
                    if bilibili_fallback_service.can_handle(url):
                        return await run_in_threadpool(bilibili_fallback_service.subtitles, url, language)
                    if self._should_use_douyin_fallback(url, format_id):
                        return await self._extract_douyin(url, format_id)
                    raise exc
            else:
                if bilibili_fallback_service.can_handle(url):
                    return await run_in_threadpool(bilibili_fallback_service.subtitles, url, language)
                if self._should_use_douyin_fallback(url, format_id):
                    return await self._extract_douyin(url, format_id)
                raise exc
        except Exception:
            if bilibili_fallback_service.can_handle(url):
                return await run_in_threadpool(bilibili_fallback_service.subtitles, url, language)
            if self._should_use_douyin_fallback(url, format_id):
                return await self._extract_douyin(url, format_id)
            raise
        track = self._select_track(info, language)
        if not track and self._should_use_douyin_fallback(url, format_id):
            return await self._extract_douyin(url, format_id)
        if not track and get_settings().browser_cookie_sources:
            info = await run_in_threadpool(self._extract_info_with_browser_cookies, url)
            track = self._select_track(info, language)
        if not track and bilibili_fallback_service.can_handle(url):
            return await run_in_threadpool(bilibili_fallback_service.subtitles, url, language)
        if not track:
            raise HTTPException(
                status_code=422,
                detail="当前视频没有可提取字幕，音频转写将在后续版本支持。",
            )

        content = await self._fetch_track(track)
        segments = self._parse(track.ext, content)
        cleaned = self._clean_segments(segments)
        if not cleaned:
            raise HTTPException(
                status_code=422,
                detail="当前视频字幕为空或无法解析，音频转写将在后续版本支持。",
            )
        return info.get("title") or "未命名视频", cleaned

    def _should_use_douyin_fallback(self, url: str, format_id: str) -> bool:
        return format_id.startswith("douyin-resolver-") or douyin_fallback_service.can_handle(url)

    async def _extract_douyin(self, url: str, format_id: str) -> tuple[str, list[TranscriptSegment]]:
        if asr_service.is_enabled():
            return await run_in_threadpool(asr_service.transcribe, url, format_id)
        return await run_in_threadpool(douyin_fallback_service.metadata_transcript, url)

    def _extract_info(self, url: str) -> dict[str, Any]:
        return self._extract_info_with_options(url, {})

    def _extract_info_with_browser_cookies(self, url: str) -> dict[str, Any]:
        last_error: HTTPException | None = None
        for browser in get_settings().browser_cookie_sources:
            try:
                return self._extract_info_with_options(url, {"cookiesfrombrowser": (browser,)})
            except HTTPException as exc:
                last_error = exc
        if last_error:
            raise last_error
        return self._extract_info(url)

    def _extract_info_with_options(self, url: str, extra_options: dict[str, Any]) -> dict[str, Any]:
        try:
            import yt_dlp
        except Exception as exc:
            raise HTTPException(status_code=503, detail="当前环境未安装 yt-dlp，无法提取字幕。") from exc

        options: dict[str, Any] = {
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
            "no_warnings": True,
            "socket_timeout": 25,
            "retries": 2,
            "fragment_retries": 2,
            "http_headers": self._headers_for(url),
            **extra_options,
        }
        cookie_file = get_settings().cookie_file_path
        if cookie_file:
            options["cookiefile"] = cookie_file

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(url, download=False)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail="字幕信息提取失败，请稍后重试或更换视频。") from exc

    def _select_track(self, info: dict[str, Any], preferred_language: str) -> SubtitleTrack | None:
        manual = self._tracks_from_map(info.get("subtitles") or {}, automatic=False)
        automatic = self._tracks_from_map(info.get("automatic_captions") or {}, automatic=True)
        return self._pick_track(manual, preferred_language) or self._pick_track(automatic, preferred_language)

    def _tracks_from_map(self, tracks: dict[str, Any], automatic: bool) -> list[SubtitleTrack]:
        results: list[SubtitleTrack] = []
        for language, items in tracks.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                url = item.get("url")
                ext = (item.get("ext") or "").lower()
                if url and ext in {"vtt", "srt", "json3"}:
                    results.append(SubtitleTrack(language=language, url=url, ext=ext, automatic=automatic))
        return results

    def _pick_track(self, tracks: list[SubtitleTrack], preferred_language: str) -> SubtitleTrack | None:
        if not tracks:
            return None

        language_order = [
            preferred_language.lower(),
            "zh-cn",
            "zh-hans",
            "zh",
            "zh-tw",
            "en",
        ]
        ext_score = {"vtt": 0, "srt": 1, "json3": 2}

        def score(track: SubtitleTrack) -> tuple[int, int]:
            language = track.language.lower()
            try:
                lang_rank = next(index for index, item in enumerate(language_order) if language.startswith(item))
            except StopIteration:
                lang_rank = len(language_order)
            return lang_rank, ext_score.get(track.ext, 9)

        return sorted(tracks, key=score)[0]

    async def _fetch_track(self, track: SubtitleTrack) -> str:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=self._headers_for(track.url)) as client:
            response = await client.get(track.url)
            response.raise_for_status()
            content = response.text
            if content.lstrip().startswith("#EXTM3U"):
                parts: list[str] = []
                for segment_url in self._playlist_segment_urls(track.url, content):
                    segment_response = await client.get(segment_url)
                    segment_response.raise_for_status()
                    parts.append(segment_response.text)
                return "\n\n".join(parts)
            return content

    def _playlist_segment_urls(self, playlist_url: str, content: str) -> list[str]:
        urls: list[str] = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(urljoin(playlist_url, line))
        return urls

    def _parse(self, ext: str, content: str) -> list[TranscriptSegment]:
        if ext == "json3":
            return self._parse_json3(content)
        return self._parse_timed_text(content)

    def _parse_json3(self, content: str) -> list[TranscriptSegment]:
        data = json.loads(content)
        segments: list[TranscriptSegment] = []
        for event in data.get("events") or []:
            start_ms = event.get("tStartMs")
            parts = event.get("segs") or []
            text = "".join(str(part.get("utf8") or "") for part in parts)
            if start_ms is None or not text.strip():
                continue
            duration_ms = event.get("dDurationMs")
            end = (start_ms + duration_ms) / 1000 if duration_ms else None
            segments.append(TranscriptSegment(start=start_ms / 1000, end=end, text=text))
        return segments

    def _parse_timed_text(self, content: str) -> list[TranscriptSegment]:
        normalized = content.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
        blocks = re.split(r"\n{2,}", normalized)
        segments: list[TranscriptSegment] = []
        for block in blocks:
            lines = [line.strip() for line in block.split("\n") if line.strip()]
            if not lines:
                continue
            timing_index = next((index for index, line in enumerate(lines) if "-->" in line), -1)
            if timing_index < 0:
                continue
            start, end = self._parse_time_range(lines[timing_index])
            text_lines = [line for line in lines[timing_index + 1 :] if not line.startswith(("WEBVTT", "NOTE"))]
            text = " ".join(text_lines)
            if text:
                segments.append(TranscriptSegment(start=start, end=end, text=text))
        return segments

    def _parse_time_range(self, line: str) -> tuple[float, float | None]:
        start_raw, end_raw = [part.strip().split(" ", 1)[0] for part in line.split("-->", 1)]
        return self._parse_timestamp(start_raw), self._parse_timestamp(end_raw)

    def _parse_timestamp(self, raw: str) -> float:
        raw = raw.replace(",", ".")
        parts = raw.split(":")
        seconds = float(parts[-1])
        if len(parts) >= 2:
            seconds += int(parts[-2]) * 60
        if len(parts) >= 3:
            seconds += int(parts[-3]) * 3600
        return seconds

    def _clean_segments(self, segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
        cleaned: list[TranscriptSegment] = []
        previous = ""
        for segment in segments:
            text = self._clean_text(segment.text)
            if not text or text == previous:
                continue
            cleaned.append(TranscriptSegment(start=segment.start, end=segment.end, text=text))
            previous = text
        return cleaned

    def _clean_text(self, value: str) -> str:
        text = value.replace("\xa0", " ")
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _headers_for(self, url: str) -> dict[str, str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if "bilibili.com" in url or "hdslb.com" in url:
            headers["Referer"] = "https://www.bilibili.com/"
        elif "douyin.com" in url or "douyinvod.com" in url or "douyinpic.com" in url or "byteimg.com" in url:
            headers["Referer"] = "https://www.douyin.com/"
        return headers


subtitle_service = SubtitleService()
