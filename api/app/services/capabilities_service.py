from app.models import CapabilitiesResponse, CapabilityItem


def get_capabilities() -> CapabilitiesResponse:
    return CapabilitiesResponse(
        mode="local_mvp",
        compliance_note="请仅下载你拥有权利或平台允许保存的内容。本项目不提供 DRM 绕过、破解或下载私密内容的能力。",
        items=[
            CapabilityItem(
                key="single_link_download",
                title="单链接下载",
                status="available",
                description="粘贴一个公开可访问的视频链接，解析信息并下载。",
            ),
            CapabilityItem(
                key="mobile_ready",
                title="手机浏览器可用",
                status="available",
                description="页面针对移动端做了输入、结果卡片和弹窗适配。",
            ),
            CapabilityItem(
                key="ai_video_analysis",
                title="AI 视频分析",
                status="available",
                description="解析视频后提取平台字幕，并通过 DeepSeek 生成摘要、大纲、知识点和视频问答。",
            ),
            CapabilityItem(
                key="batch_download",
                title="批量下载",
                status="coming_soon",
                description="后续会员能力：多链接队列、失败重试和打包下载。",
            ),
            CapabilityItem(
                key="video_summary",
                title="视频总结",
                status="coming_soon",
                description="后续接入第三方 AI，根据字幕或转写内容生成摘要。",
            ),
            CapabilityItem(
                key="subtitle_translate",
                title="字幕翻译",
                status="coming_soon",
                description="后续支持字幕提取、翻译和双语字幕下载。",
            ),
        ],
    )
