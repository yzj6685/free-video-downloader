from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException

from app.config import get_settings
from app.models import (
    AiAnalysisResponse,
    AiChatResponse,
    AiOutlineItem,
    TranscriptSegment,
)
from app.services.deepseek_client import deepseek_client
from app.services.subtitle_service import subtitle_service


@dataclass
class CachedAnalysis:
    response: AiAnalysisResponse
    transcript_text: str
    expires_at: datetime


class AiAnalysisService:
    def __init__(self) -> None:
        self._cache: dict[str, CachedAnalysis] = {}

    async def analyze(self, url: str, language: str = "zh") -> AiAnalysisResponse:
        title, segments = await subtitle_service.extract(url, language)
        transcript_text = self._segments_to_text(segments)
        ai_payload = await self._analyze_transcript(title, transcript_text)
        response = self._build_response(url, title, segments, ai_payload)
        self._cache_response(response, transcript_text)
        return response

    async def analyze_stream(self, url: str, language: str = "zh") -> AsyncIterator[dict[str, Any]]:
        yield {"type": "status", "message": "正在提取平台字幕..."}
        title, segments = await subtitle_service.extract(url, language)
        transcript_text = self._segments_to_text(segments)
        yield {
            "type": "transcript_ready",
            "title": title,
            "transcript_count": len(segments),
            "transcript_segments": [segment.model_dump() for segment in segments],
        }

        yield {"type": "status", "message": "正在流式生成视频总结..."}
        summary_parts: list[str] = []
        async for chunk in self._stream_summary(title, transcript_text):
            summary_parts.append(chunk)
            yield {"type": "summary_delta", "delta": chunk}

        yield {"type": "status", "message": "正在整理章节大纲、知识点和问答上下文..."}
        ai_payload = await self._analyze_transcript(title, transcript_text)
        streamed_summary = "".join(summary_parts).strip()
        if streamed_summary:
            ai_payload["summary"] = streamed_summary

        response = self._build_response(url, title, segments, ai_payload)
        self._cache_response(response, transcript_text)
        yield {"type": "complete", "analysis": response.model_dump()}

    async def chat(self, analysis_id: str, question: str) -> AiChatResponse:
        cached = self._get_cached(analysis_id)
        related = self._related_segments(cached.response.transcript_segments, question)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是视频学习助手。只能基于给定的视频摘要、知识点和字幕回答，"
                    "不要编造视频中没有的信息。回答要简洁、中文、适合学习复盘。"
                    "如果用户要求多个要点、步骤或原因，必须按要求分条回答，"
                    "并优先使用已给出的核心知识点。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"视频标题：{cached.response.title}\n"
                    f"摘要：{cached.response.summary}\n"
                    f"核心知识点：{'; '.join(cached.response.key_points)}\n"
                    f"相关字幕：\n{self._segments_to_text(related or cached.response.transcript_segments[:30])}\n"
                    f"问题：{question}\n"
                    "请直接回答问题；如果问题要求多个要点，请使用编号列表。"
                ),
            },
        ]
        answer = await deepseek_client.complete_text(messages)
        return AiChatResponse(answer=answer, related_segments=related, model=get_settings().deepseek_model)

    async def _analyze_transcript(self, title: str, transcript_text: str) -> dict[str, Any]:
        max_chars = get_settings().ai_max_transcript_chars
        if len(transcript_text) <= max_chars:
            return await self._request_analysis(title, transcript_text)

        chunks = self._chunk_text(transcript_text, max_chars)
        chunk_summaries: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            payload = await self._request_analysis(f"{title} - 片段 {index}", chunk)
            chunk_summaries.append(
                f"片段 {index}\n摘要：{payload.get('summary', '')}\n知识点：{'；'.join(payload.get('key_points') or [])}"
            )
        return await self._request_analysis(title, "\n\n".join(chunk_summaries))

    async def _request_analysis(self, title: str, transcript_text: str) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是专业的视频学习助手。请严格输出 JSON，不要输出 Markdown。"
                    "JSON 必须包含 summary 字符串、outline 数组、key_points 字符串数组、"
                    "suggested_questions 字符串数组。outline 每项包含 title、start、summary。"
                    "只基于字幕内容总结，不要编造。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"请分析这个视频，输出中文学习笔记。\n"
                    f"视频标题：{title}\n"
                    f"字幕内容：\n{transcript_text}"
                ),
            },
        ]

        try:
            return await deepseek_client.complete_json(messages)
        except HTTPException as first_error:
            if first_error.status_code != 502:
                raise
            return await deepseek_client.complete_json(messages)

    async def _stream_summary(self, title: str, transcript_text: str) -> AsyncIterator[str]:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是专业的视频学习助手。请用中文流式输出一段视频总结，"
                    "聚焦学习效率、核心观点和可复盘内容。只能基于字幕，不要编造。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"视频标题：{title}\n"
                    f"字幕内容：\n{transcript_text[: get_settings().ai_max_transcript_chars]}\n\n"
                    "请直接输出总结正文，不要输出标题、Markdown 或 JSON。"
                ),
            },
        ]
        async for chunk in deepseek_client.stream_text(messages, max_tokens=1200):
            yield chunk

    def _cache_response(self, response: AiAnalysisResponse, transcript_text: str) -> None:
        self._cache[response.analysis_id] = CachedAnalysis(
            response=response,
            transcript_text=transcript_text,
            expires_at=datetime.now(UTC) + timedelta(seconds=get_settings().ai_cache_ttl_seconds),
        )
        self._purge_expired()

    def _build_response(
        self,
        url: str,
        title: str,
        segments: list[TranscriptSegment],
        payload: dict[str, Any],
    ) -> AiAnalysisResponse:
        outline = []
        for item in payload.get("outline") or []:
            if not isinstance(item, dict):
                continue
            outline.append(
                AiOutlineItem(
                    title=str(item.get("title") or "章节"),
                    start=self._optional_float(item.get("start")),
                    summary=str(item.get("summary") or ""),
                )
            )

        key_points = [str(item) for item in payload.get("key_points") or [] if str(item).strip()]
        suggested = [str(item) for item in payload.get("suggested_questions") or [] if str(item).strip()]
        summary = str(payload.get("summary") or "").strip()

        if not summary:
            raise HTTPException(status_code=502, detail="AI 返回内容缺少摘要，请稍后重试。")

        return AiAnalysisResponse(
            analysis_id=str(uuid.uuid4()),
            title=title,
            source_url=url,
            summary=summary,
            outline=outline,
            key_points=key_points,
            transcript_segments=segments,
            suggested_questions=suggested[:6],
            model=get_settings().deepseek_model,
            created_at=datetime.now(UTC).isoformat(),
        )

    def _get_cached(self, analysis_id: str) -> CachedAnalysis:
        self._purge_expired()
        cached = self._cache.get(analysis_id)
        if not cached:
            raise HTTPException(status_code=404, detail="AI 分析结果已过期，请重新分析视频。")
        return cached

    def _purge_expired(self) -> None:
        now = datetime.now(UTC)
        expired = [key for key, value in self._cache.items() if value.expires_at <= now]
        for key in expired:
            self._cache.pop(key, None)

    def _related_segments(self, segments: list[TranscriptSegment], question: str) -> list[TranscriptSegment]:
        keywords = [item for item in question.replace("？", " ").replace("?", " ").split() if len(item) >= 2]
        if not keywords:
            return segments[:8]
        matched = [segment for segment in segments if any(keyword in segment.text for keyword in keywords)]
        return (matched or segments[:8])[:12]

    def _segments_to_text(self, segments: list[TranscriptSegment]) -> str:
        lines = []
        for segment in segments:
            timestamp = self._format_seconds(segment.start)
            lines.append(f"[{timestamp}] {segment.text}")
        return "\n".join(lines)

    def _format_seconds(self, value: float) -> str:
        total = int(value)
        minutes, seconds = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _chunk_text(self, text: str, max_chars: int) -> list[str]:
        lines = text.splitlines()
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for line in lines:
            if current and current_len + len(line) + 1 > max_chars:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            current.append(line)
            current_len += len(line) + 1
        if current:
            chunks.append("\n".join(current))
        return chunks

    def _optional_float(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


ai_analysis_service = AiAnalysisService()
