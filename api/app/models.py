import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ProbeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=3000)

    @field_validator("url")
    @classmethod
    def extract_first_url(cls, value: str) -> str:
        match = re.search(r"https?://[^\s]+", value.strip())
        if not match:
            raise ValueError("请输入正确的视频链接。")
        return match.group(0).rstrip("，。；;)")


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
