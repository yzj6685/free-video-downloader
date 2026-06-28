from app.models import BillingPlan, BillingPlansResponse, PlanFeature


def get_plans() -> BillingPlansResponse:
    return BillingPlansResponse(
        plans=[
            BillingPlan(
                id="free",
                name="免费试用",
                price="¥0",
                period="体验",
                badge="当前可用",
                description="适合偶尔下载公开视频的轻量用户。",
                cta="继续免费使用",
                features=[
                    PlanFeature(label="单链接解析"),
                    PlanFeature(label="基础格式下载"),
                    PlanFeature(label="移动端网页使用"),
                ],
            ),
            BillingPlan(
                id="pro",
                name="Pro 会员",
                price="¥19.9",
                period="月",
                badge="推荐",
                description="适合学习、剪辑和素材整理的高频用户。",
                cta="开通 Pro",
                features=[
                    PlanFeature(label="批量下载", highlighted=True),
                    PlanFeature(label="高清格式优先", highlighted=True),
                    PlanFeature(label="视频总结"),
                    PlanFeature(label="字幕翻译"),
                    PlanFeature(label="更快下载队列"),
                ],
            ),
            BillingPlan(
                id="team",
                name="团队版",
                price="¥99",
                period="月",
                badge="进阶",
                description="适合课程团队、运营团队和内容团队。",
                cta="联系开通",
                features=[
                    PlanFeature(label="多人额度"),
                    PlanFeature(label="任务历史"),
                    PlanFeature(label="批量打包"),
                    PlanFeature(label="团队素材管理"),
                ],
            ),
        ]
    )
