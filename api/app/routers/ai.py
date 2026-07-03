from fastapi import APIRouter, status

from app.models import ComingSoonResponse

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post(
    "/summary",
    response_model=ComingSoonResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def video_summary() -> ComingSoonResponse:
    return ComingSoonResponse(
        status="coming_soon",
        feature="video_summary",
        message="旧版视频总结入口已停用，请使用 /api/ai/analyze 或 /api/ai/analyze-stream。",
    )


@router.post(
    "/translate-subtitles",
    response_model=ComingSoonResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def translate_subtitles() -> ComingSoonResponse:
    return ComingSoonResponse(
        status="coming_soon",
        feature="subtitle_translate",
        message="当前产品未提供字幕翻译，请使用 AI 总结、字幕文本和视频问答功能。",
    )
