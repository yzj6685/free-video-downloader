from functools import lru_cache
from pathlib import Path
from os import getenv


class Settings:
    def __init__(self) -> None:
        self.ytdlp_cookie_file = getenv("YTDLP_COOKIE_FILE", "").strip()
        self.douyin_resolver_endpoint = getenv("DOUYIN_RESOLVER_ENDPOINT", "").strip()
        self.ffmpeg_location = getenv("FFMPEG_LOCATION", "").strip()

    @property
    def cookie_file_path(self) -> str | None:
        if not self.ytdlp_cookie_file:
            return None
        path = Path(self.ytdlp_cookie_file).expanduser()
        return str(path) if path.exists() else None

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
