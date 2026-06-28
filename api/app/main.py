from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import ai, billing, video

app = FastAPI(
    title="万能视频下载器 API",
    description="本地演示版：单链接视频解析、下载和会员能力预留。",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(video.router)
app.include_router(ai.router)
app.include_router(billing.router)
