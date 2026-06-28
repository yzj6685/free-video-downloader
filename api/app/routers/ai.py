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
        message="视频总结是会员高级能力，首版仅预留接口，后续将接入第三方 AI。",
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
        message="字幕翻译是会员高级能力，首版仅预留接口，后续将接入第三方 AI。",
    )
