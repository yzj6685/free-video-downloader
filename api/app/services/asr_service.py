from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.models import TranscriptSegment
from app.services.douyin_fallback import douyin_fallback_service


class AsrService:
    def is_enabled(self) -> bool:
        settings = get_settings()
        return self._provider() == "siliconflow" and bool(settings.siliconflow_api_key)

    def transcribe(self, url: str, format_id: str = "best") -> tuple[str, list[TranscriptSegment]]:
        settings = get_settings()
        if self._provider() != "siliconflow" or not settings.siliconflow_api_key:
            raise HTTPException(status_code=503, detail="尚未配置 ASR 服务，无法根据音频内容生成字幕。")

        if not format_id.startswith("douyin-resolver-") and douyin_fallback_service.can_handle(url):
            format_id = "douyin-resolver-nested"
        if not format_id.startswith("douyin-resolver-"):
            raise HTTPException(status_code=422, detail="当前 ASR 兜底暂只支持已解析的抖音视频。")

        direct = douyin_fallback_service.direct_url(url, format_id)
        text = self._transcribe_media_url(direct.url, source_url=url)
        segments = self._segments_from_text(text)
        if not segments:
            raise HTTPException(status_code=502, detail="ASR 转写结果为空，请稍后重试或更换视频。")
        return Path(direct.filename).stem, segments

    def _provider(self) -> str:
        settings = get_settings()
        return settings.asr_provider or ("siliconflow" if settings.siliconflow_api_key else "")

    def _transcribe_media_url(self, media_url: str, source_url: str) -> str:
        audio_path = self._extract_audio(media_url, source_url)
        try:
            return self._siliconflow_transcribe(audio_path)
        finally:
            audio_path.unlink(missing_ok=True)

    def _extract_audio(self, media_url: str, source_url: str) -> Path:
        ffmpeg = self._ffmpeg_path()
        target = Path(tempfile.NamedTemporaryFile(prefix="asr-", suffix=".mp3", delete=False).name)
        headers = self._ffmpeg_headers(source_url)
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-headers",
            headers,
            "-i",
            media_url,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-t",
            str(get_settings().asr_max_seconds),
            "-b:a",
            "48k",
            str(target),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=get_settings().asr_max_seconds + 120)
        except subprocess.CalledProcessError as exc:
            target.unlink(missing_ok=True)
            detail = (exc.stderr or exc.stdout or "ffmpeg 音频提取失败").strip()
            raise HTTPException(status_code=502, detail=f"音频提取失败：{detail[:300]}") from exc
        except subprocess.TimeoutExpired as exc:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=504, detail="音频提取超时，请稍后重试或更换较短视频。") from exc

        if not target.exists() or target.stat().st_size <= 0:
            raise HTTPException(status_code=502, detail="音频提取失败：未生成有效音频文件。")
        if target.stat().st_size > 50 * 1024 * 1024:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=413, detail="音频文件超过 SiliconFlow 50MB 限制，请选择较短视频。")
        return target

    def _siliconflow_transcribe(self, audio_path: Path) -> str:
        settings = get_settings()
        endpoint = f"{settings.siliconflow_base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {settings.siliconflow_api_key}"}
        with audio_path.open("rb") as file:
            files = {"file": (audio_path.name, file, "audio/mpeg")}
            data = {"model": settings.siliconflow_asr_model}
            try:
                response = httpx.post(endpoint, headers=headers, files=files, data=data, timeout=120)
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail="SiliconFlow ASR 请求失败，请稍后重试。") from exc

        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="SiliconFlow API Key 无效，请检查配置。")
        if response.status_code == 402:
            raise HTTPException(status_code=402, detail="SiliconFlow 余额不足，请充值后重试。")
        if response.status_code == 429:
            raise HTTPException(status_code=429, detail="SiliconFlow ASR 触发限流，请稍后重试。")
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"SiliconFlow ASR 失败：{response.text[:300]}")

        payload = response.json()
        text = payload.get("text")
        return str(text).strip() if text else ""

    def _segments_from_text(self, text: str) -> list[TranscriptSegment]:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return []

        parts = [part.strip() for part in re.split(r"(?<=[。！？!?；;])\s*", normalized) if part.strip()]
        if len(parts) <= 1:
            parts = [normalized[index : index + 80].strip() for index in range(0, len(normalized), 80)]

        segments: list[TranscriptSegment] = []
        cursor = 0.0
        for part in parts:
            duration = max(2.0, min(12.0, len(part) / 6))
            segments.append(TranscriptSegment(start=round(cursor, 2), end=round(cursor + duration, 2), text=part))
            cursor += duration
        return segments

    def _ffmpeg_path(self) -> str:
        ffmpeg_dir = get_settings().ffmpeg_location_path
        if ffmpeg_dir:
            directory = Path(ffmpeg_dir)
            windows_binary = directory / "ffmpeg.exe"
            if windows_binary.exists():
                return str(windows_binary)
            unix_binary = directory / "ffmpeg"
            if unix_binary.exists():
                return str(unix_binary)
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
        raise HTTPException(status_code=503, detail="当前环境缺少 ffmpeg，无法提取音频。")

    def _ffmpeg_headers(self, source_url: str) -> str:
        lines = [
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
        ]
        if "douyin.com" in source_url or "iesdouyin.com" in source_url:
            lines.append("Referer: https://www.douyin.com/")
        return "\r\n".join(lines) + "\r\n"


asr_service = AsrService()
