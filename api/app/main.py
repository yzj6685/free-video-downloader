from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import ai, ai_analysis, auth, billing, video

app = FastAPI(
    title="一手遮天视频下载总结器 API",
    description="公开视频解析下载、AI 视频总结、账号登录和 Stripe Pro 会员权益。",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(video.router)
app.include_router(ai.router)
app.include_router(ai_analysis.router)
app.include_router(billing.router)
app.include_router(auth.router)
