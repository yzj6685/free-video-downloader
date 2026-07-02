import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models import (
    AiAnalysisRequest,
    AiAnalysisResponse,
    AiChatRequest,
    AiChatResponse,
)
from app.services.ai_analysis_service import ai_analysis_service

router = APIRouter(prefix="/api/ai", tags=["ai-analysis"])


@router.post("/analyze", response_model=AiAnalysisResponse)
async def analyze_video(payload: AiAnalysisRequest) -> AiAnalysisResponse:
    return await ai_analysis_service.analyze(str(payload.url), payload.language, payload.format_id)


@router.post("/analyze-stream")
async def analyze_video_stream(payload: AiAnalysisRequest) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in ai_analysis_service.analyze_stream(str(payload.url), payload.language, payload.format_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except HTTPException as exc:
            event = {"type": "error", "status_code": exc.status_code, "message": exc.detail}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception:
            event = {"type": "error", "status_code": 500, "message": "AI 分析失败，请稍后重试。"}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat", response_model=AiChatResponse)
async def chat_with_video(payload: AiChatRequest) -> AiChatResponse:
    return await ai_analysis_service.chat(payload.analysis_id, payload.question)


@router.post("/chat-stream")
async def chat_with_video_stream(payload: AiChatRequest) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in ai_analysis_service.chat_stream(payload.analysis_id, payload.question):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except HTTPException as exc:
            event = {"type": "error", "status_code": exc.status_code, "message": exc.detail}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception:
            event = {"type": "error", "status_code": 500, "message": "AI 问答失败，请稍后重试。"}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
