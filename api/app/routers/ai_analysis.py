import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.models import (
    AiAnalysisRequest,
    AiAnalysisResponse,
    AiChatRequest,
    AiChatResponse,
)
from app.services.ai_analysis_service import ai_analysis_service
from app.services.auth_service import auth_service
from app.services.billing_service import billing_service

router = APIRouter(prefix="/api/ai", tags=["ai-analysis"])


def billing_email_from_auth(authorization: str | None) -> str:
    prefix = "Bearer "
    token = authorization[len(prefix) :].strip() if authorization and authorization.startswith(prefix) else None
    return auth_service.me(token).email


@router.post("/analyze", response_model=AiAnalysisResponse)
async def analyze_video(payload: AiAnalysisRequest, authorization: str | None = Header(default=None)) -> AiAnalysisResponse:
    billing_email = billing_email_from_auth(authorization)
    billing_service.ensure_ai_analysis_allowed(billing_email)
    result = await ai_analysis_service.analyze(str(payload.url), payload.language, payload.format_id)
    billing_service.record_ai_analysis_success(billing_email)
    return result


@router.post("/analyze-stream")
async def analyze_video_stream(payload: AiAnalysisRequest, authorization: str | None = Header(default=None)) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        try:
            billing_email = billing_email_from_auth(authorization)
            billing_service.ensure_ai_analysis_allowed(billing_email)
            async for event in ai_analysis_service.analyze_stream(str(payload.url), payload.language, payload.format_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") == "complete":
                    billing_service.record_ai_analysis_success(billing_email)
        except HTTPException as exc:
            event = {"type": "error", "status_code": exc.status_code, "message": exc.detail}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception:
            event = {"type": "error", "status_code": 500, "message": "AI 分析失败，请稍后重试。"}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat", response_model=AiChatResponse)
async def chat_with_video(payload: AiChatRequest, authorization: str | None = Header(default=None)) -> AiChatResponse:
    billing_email = billing_email_from_auth(authorization)
    billing_service.ensure_ai_chat_allowed(billing_email)
    return await ai_analysis_service.chat(payload.analysis_id, payload.question)


@router.post("/chat-stream")
async def chat_with_video_stream(payload: AiChatRequest, authorization: str | None = Header(default=None)) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        try:
            billing_email = billing_email_from_auth(authorization)
            billing_service.ensure_ai_chat_allowed(billing_email)
            async for event in ai_analysis_service.chat_stream(payload.analysis_id, payload.question):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except HTTPException as exc:
            event = {"type": "error", "status_code": exc.status_code, "message": exc.detail}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception:
            event = {"type": "error", "status_code": 500, "message": "AI 问答失败，请稍后重试。"}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
