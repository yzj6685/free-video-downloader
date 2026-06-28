from fastapi import APIRouter

from app.models import BillingPlansResponse
from app.services.billing_service import get_plans

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/plans", response_model=BillingPlansResponse)
def plans() -> BillingPlansResponse:
    return get_plans()
