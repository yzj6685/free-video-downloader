from functools import lru_cache
from pathlib import Path
from os import getenv


class Settings:
    def __init__(self) -> None:
        self.ytdlp_cookie_file = getenv("YTDLP_COOKIE_FILE", "").strip()
        self.ytdlp_browser_cookies = getenv("YTDLP_BROWSER_COOKIES", "chrome,edge").strip()
        self.douyin_resolver_endpoint = getenv("DOUYIN_RESOLVER_ENDPOINT", "").strip()
        self.ffmpeg_location = getenv("FFMPEG_LOCATION", "").strip()
        self.deepseek_api_key = getenv("DEEPSEEK_API_KEY", "").strip()
        self.deepseek_base_url = getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
        self.deepseek_model = getenv("DEEPSEEK_MODEL", "deepseek-v4-pro").strip()
        self.ai_cache_ttl_seconds = int(getenv("AI_CACHE_TTL_SECONDS", "3600"))
        self.ai_max_transcript_chars = int(getenv("AI_MAX_TRANSCRIPT_CHARS", "24000"))
        self.asr_provider = getenv("ASR_PROVIDER", "").strip().lower()
        self.asr_max_seconds = int(getenv("ASR_MAX_SECONDS", "900"))
        self.siliconflow_api_key = getenv("SILICONFLOW_API_KEY", "").strip()
        self.siliconflow_base_url = getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1").strip().rstrip("/")
        self.siliconflow_asr_model = getenv("SILICONFLOW_ASR_MODEL", "FunAudioLLM/SenseVoiceSmall").strip()

    @property
    def cookie_file_path(self) -> str | None:
        if not self.ytdlp_cookie_file:
            return None
        path = Path(self.ytdlp_cookie_file).expanduser()
        return str(path) if path.exists() else None

    @property
    def browser_cookie_sources(self) -> list[str]:
        if not self.ytdlp_browser_cookies:
            return []
        return [
            item.strip().lower()
            for item in self.ytdlp_browser_cookies.split(",")
            if item.strip()
        ]

    @property
    def ffmpeg_location_path(self) -> str | None:
        candidates: list[Path] = []
        if self.ffmpeg_location:
            candidates.append(Path(self.ffmpeg_location).expanduser())

        project_root = Path(__file__).resolve().parents[2]
        candidates.append(project_root / "tools" / "ffmpeg" / "bin")

        for candidate in candidates:
            if candidate.is_file() and candidate.name.lower().startswith("ffmpeg"):
                return str(candidate.parent)
            if (candidate / "ffmpeg.exe").exists() and (candidate / "ffprobe.exe").exists():
                return str(candidate)
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
