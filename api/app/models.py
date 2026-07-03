import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ProbeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=3000)

    @field_validator("url")
    @classmethod
    def extract_first_url(cls, value: str) -> str:
        text = value.strip()
        match = re.search(r"https?://[^\s]+", text, flags=re.IGNORECASE)
        if not match:
            match = re.search(
                r"(?<!@)\b(?:www\.)?[a-z0-9][a-z0-9-]*(?:\.[a-z0-9][a-z0-9-]*)+(?:/[^\s]*)?",
                text,
                flags=re.IGNORECASE,
            )
        if not match:
            raise ValueError("请输入正确的视频链接。")
        url = match.group(0).rstrip("，。；;)）]")
        if not re.match(r"https?://", url, flags=re.IGNORECASE):
            url = f"https://{url}"
        return url


class DownloadRequest(BaseModel):
    url: str = Field(min_length=1, max_length=3000)
    format_id: str = Field(default="best", min_length=1, max_length=120)
    delivery: Literal["auto", "direct", "proxy"] = "auto"

    @field_validator("url")
    @classmethod
    def extract_first_url(cls, value: str) -> str:
        return ProbeRequest.extract_first_url(value)


class VideoFormat(BaseModel):
    format_id: str
    label: str
    extension: str | None = None
    resolution: str | None = None
    filesize: int | None = None
    has_video: bool = True
    has_audio: bool = True


class ProbeResponse(BaseModel):
    title: str
    url: str
    extractor: str | None = None
    uploader: str | None = None
    duration: int | None = None
    thumbnail: str | None = None
    formats: list[VideoFormat]
    recommended_format_id: str
    may_require_proxy: bool = False


class HealthResponse(BaseModel):
    status: Literal["ok"]
    yt_dlp_available: bool
    yt_dlp_version: str | None = None
    ffmpeg_available: bool
    cookie_file_configured: bool = False
    message: str


class CapabilityItem(BaseModel):
    key: str
    title: str
    status: Literal["available", "coming_soon"]
    description: str


class CapabilitiesResponse(BaseModel):
    mode: str
    items: list[CapabilityItem]
    compliance_note: str


class DirectDownloadResponse(BaseModel):
    type: Literal["direct", "proxy"]
    url: str
    filename: str
    expires_quickly: bool = True


class ComingSoonResponse(BaseModel):
    status: Literal["coming_soon"]
    feature: str
    message: str


class PlanFeature(BaseModel):
    label: str
    highlighted: bool = False


class BillingPlan(BaseModel):
    id: str
    name: str
    price: str
    period: str
    badge: str | None = None
    description: str
    features: list[PlanFeature]
    cta: str


class BillingPlansResponse(BaseModel):
    plans: list[BillingPlan]


class CheckoutRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    plan_id: str = Field(default="pro", min_length=1, max_length=40)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized):
            raise ValueError("请输入可用于接收支付凭证的邮箱。")
        return normalized


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class EntitlementResponse(BaseModel):
    email: str
    plan_id: str | None = None
    active: bool = False
    free_limit: int = 3
    free_used: int = 0
    free_remaining: int = 3


class AuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized):
            raise ValueError("请输入有效邮箱。")
        return normalized


class UserResponse(BaseModel):
    id: int
    email: str
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class TranscriptSegment(BaseModel):
    start: float
    end: float | None = None
    text: str


class AiOutlineItem(BaseModel):
    title: str
    start: float | None = None
    summary: str


class AiAnalysisRequest(BaseModel):
    url: str = Field(min_length=1, max_length=3000)
    format_id: str = Field(default="best", min_length=1, max_length=120)
    language: str = Field(default="zh", min_length=2, max_length=16)
    billing_email: str | None = Field(default=None, max_length=254)

    @field_validator("url")
    @classmethod
    def extract_first_url(cls, value: str) -> str:
        return ProbeRequest.extract_first_url(value)


class AiAnalysisResponse(BaseModel):
    analysis_id: str
    title: str
    source_url: str
    summary: str
    outline: list[AiOutlineItem]
    key_points: list[str]
    transcript_segments: list[TranscriptSegment]
    suggested_questions: list[str]
    model: str
    created_at: str


class AiChatRequest(BaseModel):
    analysis_id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=1000)
    billing_email: str | None = Field(default=None, max_length=254)


class AiChatResponse(BaseModel):
    answer: str
    related_segments: list[TranscriptSegment]
    model: str
