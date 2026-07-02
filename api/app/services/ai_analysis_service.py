from __future__ import annotations

import uuid
import re
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

    async def analyze(self, url: str, language: str = "zh", format_id: str = "best") -> AiAnalysisResponse:
        title, segments = await subtitle_service.extract(url, language, format_id)
        transcript_text = self._segments_to_text(segments)
        ai_payload = await self._summarize_transcript(title, transcript_text)
        response = self._build_response(url, title, segments, ai_payload)
        self._cache_response(response, transcript_text)
        return response

    async def analyze_stream(self, url: str, language: str = "zh", format_id: str = "best") -> AsyncIterator[dict[str, Any]]:
        if "douyin.com" in url or "iesdouyin.com" in url or format_id.startswith("douyin-resolver-"):
            yield {
                "type": "status",
                "stage": "asr",
                "progress": 12,
                "message": "正在提取音频并进行语音转写，短视频通常需要 30-90 秒...",
            }
        else:
            yield {
                "type": "status",
                "stage": "subtitle",
                "progress": 18,
                "message": "AI 正在读取视频字幕...",
            }
        title, segments = await subtitle_service.extract(url, language, format_id)
        transcript_text = self._segments_to_text(segments)
        yield {
            "type": "transcript_ready",
            "title": title,
            "transcript_count": len(segments),
            "transcript_segments": [segment.model_dump() for segment in segments],
        }

        yield {"type": "status", "stage": "summary", "progress": 88, "message": "字幕已准备好，AI 正在总结视频重点..."}
        note_parts: list[str] = []
        async for chunk in self._stream_learning_note(title, transcript_text):
            note_parts.append(chunk)
            yield {"type": "summary_delta", "delta": chunk}

        streamed_note = self._normalize_outline_markdown("".join(note_parts).strip())
        ai_payload = self._payload_from_markdown_note(streamed_note)
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
                    "你是视频学习助手。只能基于给定的视频摘要和字幕回答，"
                    "不要编造视频中没有的信息。回答要简洁、中文、适合学习复盘。"
                    "如果用户要求多个要点、步骤或原因，必须按要求分条回答，"
                    "并尽量引用字幕中的关键信息。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"视频标题：{cached.response.title}\n"
                    f"摘要：{cached.response.summary}\n"
                    f"相关字幕：\n{self._segments_to_text(related or cached.response.transcript_segments[:30])}\n"
                    f"问题：{question}\n"
                    "请直接回答问题；如果问题要求多个要点，请使用编号列表。"
                ),
            },
        ]
        answer = await deepseek_client.complete_text(messages)
        return AiChatResponse(answer=answer, related_segments=related, model=get_settings().deepseek_model)

    async def chat_stream(self, analysis_id: str, question: str) -> AsyncIterator[dict[str, Any]]:
        cached = self._get_cached(analysis_id)
        related = self._related_segments(cached.response.transcript_segments, question)
        yield {"type": "related_segments", "related_segments": [segment.model_dump() for segment in related]}
        messages = [
            {
                "role": "system",
                "content": (
                    "你是视频学习助手。只能基于给定的视频摘要和字幕回答，"
                    "不要编造视频中没有的信息。回答要简洁、中文、适合学习复盘。"
                    "如果用户要求多个要点、步骤或原因，必须按要求分条回答。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"视频标题：{cached.response.title}\n"
                    f"摘要：{cached.response.summary}\n"
                    f"相关字幕：\n{self._segments_to_text(related or cached.response.transcript_segments[:30])}\n"
                    f"问题：{question}\n"
                    "请直接回答问题；如果问题要求多个要点，请使用编号列表。"
                ),
            },
        ]
        parts: list[str] = []
        async for chunk in deepseek_client.stream_text(messages):
            parts.append(chunk)
            yield {"type": "answer_delta", "delta": chunk}
        yield {
            "type": "complete",
            "answer": "".join(parts).strip(),
            "related_segments": [segment.model_dump() for segment in related],
            "model": get_settings().deepseek_model,
        }

    async def _summarize_transcript(self, title: str, transcript_text: str) -> dict[str, Any]:
        max_chars = get_settings().ai_max_transcript_chars
        if len(transcript_text) <= max_chars:
            parts = [chunk async for chunk in self._stream_learning_note(title, transcript_text)]
            note = "".join(parts).strip()
            if not note:
                raise HTTPException(status_code=502, detail="AI 返回内容缺少摘要，请稍后重试。")
            return self._payload_from_markdown_note(self._normalize_outline_markdown(note))

        chunks = self._chunk_text(transcript_text, max_chars)
        chunk_summaries: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            parts = [part async for part in self._stream_learning_note(f"{title} - 片段 {index}", chunk)]
            chunk_summaries.append(f"片段 {index}\n{''.join(parts).strip()}")
        parts = [part async for part in self._stream_learning_note(title, "\n\n".join(chunk_summaries))]
        note = "".join(parts).strip()
        if not note:
            raise HTTPException(status_code=502, detail="AI 返回内容缺少摘要，请稍后重试。")
        return self._payload_from_markdown_note(self._normalize_outline_markdown(note))

    async def _stream_learning_note(self, title: str, transcript_text: str) -> AsyncIterator[str]:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是专业的视频内容整理助手。请用中文流式输出通用 Markdown 摘要。"
                    "用户解析的视频可能是学习、技术、美食、旅游、生活、娱乐等任意内容，"
                    "所以不要固定写成学习笔记。只能基于字幕、公开视频文案或标题，不要编造。"
                    "必须包含以下二级标题：## 视频概述、## 内容大纲。"
                    "视频概述用 1 到 2 个短段落说明视频主要内容，避免冗长。"
                    "内容大纲要精简，最多 5 个一级模块；每个模块最多 3 个子项。"
                    "内容大纲使用标准 Markdown：一级条目用 `1. **功能点**`，不要带时间戳；"
                    "子项必须缩进两个空格并统一用 `  - **功能名**：解释`，必要时才用四个空格的三级缩进 `    - 细节`。"
                    "不要使用 `•`、`·`、`●`。关键信息、功能名、核心术语用 ** ** 加粗。"
                    "不要输出 JSON。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"视频标题：{title}\n"
                    f"字幕或文案内容：\n{transcript_text[: get_settings().ai_max_transcript_chars]}\n\n"
                    "请直接输出 Markdown，不要输出 JSON，不要解释你的生成过程。"
                ),
            },
        ]
        async for chunk in deepseek_client.stream_text(messages, max_tokens=2400):
            yield chunk

    def _payload_from_markdown_note(self, note: str) -> dict[str, Any]:
        summary_section = self._extract_first_markdown_section(note, ["视频概述", "视频总结"]) or note
        outline_section = self._extract_first_markdown_section(note, ["内容大纲", "章节大纲"])
        key_points_section = self._extract_first_markdown_section(note, ["核心知识点", "重点内容"])
        questions_section = self._extract_first_markdown_section(note, ["可追问问题", "延伸问题"])
        return {
            "summary": note,
            "outline": self._parse_outline_section(outline_section),
            "key_points": self._parse_list_section(key_points_section),
            "suggested_questions": self._parse_list_section(questions_section),
            "plain_summary": summary_section.strip(),
        }

    def _normalize_outline_markdown(self, note: str) -> str:
        lines: list[str] = []
        in_outline = False
        for raw_line in note.replace("\r\n", "\n").split("\n"):
            stripped = raw_line.strip()
            if stripped.startswith("## "):
                in_outline = stripped.lstrip("#").strip() in {"内容大纲", "章节大纲"}
                lines.append(raw_line.rstrip())
                continue
            line = re.sub(r"^(\s*)[•·●]\s+", r"\1- ", raw_line)
            if in_outline:
                line = re.sub(r"\s*\[\d{1,2}:\d{2}(?::\d{2})?\]", "", line)
            lines.append(line.rstrip())
        return "\n".join(lines).strip()

    def _extract_first_markdown_section(self, markdown: str, headings: list[str]) -> str:
        for heading in headings:
            section = self._extract_markdown_section(markdown, heading)
            if section:
                return section
        return ""

    def _extract_markdown_section(self, markdown: str, heading: str) -> str:
        lines = markdown.replace("\r\n", "\n").split("\n")
        collected: list[str] = []
        in_section = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## "):
                current_heading = stripped.lstrip("#").strip()
                if in_section:
                    break
                in_section = current_heading == heading
                continue
            if in_section:
                collected.append(line)
        return "\n".join(collected).strip()

    def _parse_list_section(self, section: str) -> list[str]:
        items: list[str] = []
        for raw_line in section.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line = line.lstrip("-* ").strip()
            if len(line) > 2 and line[0].isdigit():
                line = line.split(".", 1)[-1].split(")", 1)[-1].strip()
            if line:
                items.append(line)
        return items[:8]

    def _parse_outline_section(self, section: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for raw_line in section.splitlines():
            line = raw_line.strip().lstrip("-* ").strip()
            if not line:
                continue
            if len(line) > 2 and line[0].isdigit():
                line = line.split(".", 1)[-1].split(")", 1)[-1].strip()
            start = None
            time_match = re.search(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]", line)
            if time_match:
                start = self._parse_timestamp(time_match.group(1))
                line = line.replace(time_match.group(0), "").strip()
            if "：" in line:
                title, summary = line.split("：", 1)
            elif ":" in line:
                title, summary = line.split(":", 1)
            else:
                title, summary = line, ""
            title = title.replace("**", "").replace("__", "").strip()
            summary = summary.replace("**", "").replace("__", "").strip()
            items.append({"title": title.strip() or "章节", "start": start, "summary": summary.strip()})
        return items[:8]

    def _parse_timestamp(self, value: str) -> float | None:
        parts = value.split(":")
        try:
            numbers = [int(part) for part in parts]
        except ValueError:
            return None
        if len(numbers) == 2:
            minutes, seconds = numbers
            return float(minutes * 60 + seconds)
        if len(numbers) == 3:
            hours, minutes, seconds = numbers
            return float(hours * 3600 + minutes * 60 + seconds)
        return None

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
