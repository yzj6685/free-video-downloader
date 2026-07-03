from fastapi import APIRouter, Header, Request

from app.models import BillingPlansResponse, CheckoutRequest, CheckoutResponse, EntitlementResponse
from app.services.billing_service import billing_service, get_plans

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/plans", response_model=BillingPlansResponse)
def plans() -> BillingPlansResponse:
    return get_plans()


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout(payload: CheckoutRequest) -> CheckoutResponse:
    return billing_service.create_checkout(payload.email, payload.plan_id)


@router.get("/entitlement", response_model=EntitlementResponse)
def entitlement(email: str) -> EntitlementResponse:
    return billing_service.entitlement_for_email(email)


@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(default=None)) -> dict[str, bool | str]:
    payload = await request.body()
    event = billing_service.construct_webhook_event(payload, stripe_signature)
    return billing_service.handle_webhook_event(event)
