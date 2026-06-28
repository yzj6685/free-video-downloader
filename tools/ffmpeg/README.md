# FFmpeg

This directory is reserved for the local FFmpeg runtime used by the FastAPI backend.

The actual binaries are intentionally ignored by Git because they are large:

- `bin/ffmpeg.exe`
- `bin/ffprobe.exe`
- `bin/ffplay.exe`

Install or restore them with:

```powershell
.\scripts\install-ffmpeg.ps1
```

The backend checks `FFMPEG_LOCATION` first, then falls back to `tools/ffmpeg/bin`.
