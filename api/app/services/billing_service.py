from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.config import get_settings
from app.models import (
    BillingPlan,
    BillingPlansResponse,
    CheckoutResponse,
    EntitlementResponse,
    PlanFeature,
)


PRO_PLAN_ID = "pro"
FREE_ANALYSIS_LIMIT = 3
_lock = threading.Lock()


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def get_plans() -> BillingPlansResponse:
    return BillingPlansResponse(
        plans=[
            BillingPlan(
                id="free",
                name="免费版",
                price="¥0",
                period="3 次 AI 总结",
                badge="当前可用",
                description="适合轻量下载和体验 AI 视频总结的新用户。",
                cta="继续免费使用",
                features=[
                    PlanFeature(label="单链接解析"),
                    PlanFeature(label="公开视频下载"),
                    PlanFeature(label="AI 视频总结 3 次", highlighted=True),
                ],
            ),
            BillingPlan(
                id=PRO_PLAN_ID,
                name="Pro 会员",
                price="¥19.9",
                period="一次性",
                badge="推荐",
                description="适合需要无限 AI 视频总结、问答和学习笔记的高频用户。",
                cta="开通 Pro",
                features=[
                    PlanFeature(label="无限 AI 视频总结", highlighted=True),
                    PlanFeature(label="AI 视频问答", highlighted=True),
                    PlanFeature(label="字幕文本整理"),
                    PlanFeature(label="思维导图生成"),
                ],
            ),
        ]
    )


class BillingStore:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or get_settings().billing_database_path

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with _lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS billing_orders (
                    stripe_session_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    amount_total INTEGER,
                    currency TEXT,
                    status TEXT NOT NULL,
                    stripe_customer_id TEXT,
                    stripe_payment_intent_id TEXT,
                    stripe_event_id TEXT,
                    raw_payload TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS billing_entitlements (
                    email TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    source_session_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_usage (
                    email TEXT PRIMARY KEY,
                    used_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def record_checkout_session(self, session: dict[str, Any], email: str, plan_id: str) -> None:
        self.initialize()
        now = utc_now()
        with _lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO billing_orders (
                    stripe_session_id, email, plan_id, amount_total, currency, status,
                    stripe_customer_id, stripe_payment_intent_id, raw_payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stripe_session_id) DO UPDATE SET
                    email=excluded.email,
                    plan_id=excluded.plan_id,
                    amount_total=excluded.amount_total,
                    currency=excluded.currency,
                    status=excluded.status,
                    stripe_customer_id=excluded.stripe_customer_id,
                    stripe_payment_intent_id=excluded.stripe_payment_intent_id,
                    raw_payload=excluded.raw_payload,
                    updated_at=excluded.updated_at
                """,
                (
                    session.get("id"),
                    email,
                    plan_id,
                    session.get("amount_total"),
                    session.get("currency"),
                    session.get("payment_status") or session.get("status") or "open",
                    session.get("customer"),
                    session.get("payment_intent"),
                    json.dumps(session, ensure_ascii=False, default=str),
                    now,
                    now,
                ),
            )

    def fulfill_checkout_session(self, session: dict[str, Any], event_id: str | None = None) -> bool:
        self.initialize()
        email = normalize_email(
            session.get("customer_email")
            or ((session.get("customer_details") or {}).get("email") if isinstance(session.get("customer_details"), dict) else None)
            or ((session.get("metadata") or {}).get("email") if isinstance(session.get("metadata"), dict) else None)
        )
        plan_id = str((session.get("metadata") or {}).get("plan_id") or PRO_PLAN_ID)
        session_id = str(session.get("id") or "")
        if not email or not session_id:
            return False

        status = "paid" if session.get("payment_status") == "paid" else str(session.get("payment_status") or "unpaid")
        now = utc_now()
        with _lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO billing_orders (
                    stripe_session_id, email, plan_id, amount_total, currency, status,
                    stripe_customer_id, stripe_payment_intent_id, stripe_event_id,
                    raw_payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stripe_session_id) DO UPDATE SET
                    email=excluded.email,
                    plan_id=excluded.plan_id,
                    amount_total=excluded.amount_total,
                    currency=excluded.currency,
                    status=excluded.status,
                    stripe_customer_id=excluded.stripe_customer_id,
                    stripe_payment_intent_id=excluded.stripe_payment_intent_id,
                    stripe_event_id=excluded.stripe_event_id,
                    raw_payload=excluded.raw_payload,
                    updated_at=excluded.updated_at
                """,
                (
                    session_id,
                    email,
                    plan_id,
                    session.get("amount_total"),
                    session.get("currency"),
                    status,
                    session.get("customer"),
                    session.get("payment_intent"),
                    event_id,
                    json.dumps(session, ensure_ascii=False, default=str),
                    now,
                    now,
                ),
            )
            if status == "paid":
                connection.execute(
                    """
                    INSERT INTO billing_entitlements (
                        email, plan_id, active, source_session_id, created_at, updated_at
                    ) VALUES (?, ?, 1, ?, ?, ?)
                    ON CONFLICT(email) DO UPDATE SET
                        plan_id=excluded.plan_id,
                        active=1,
                        source_session_id=excluded.source_session_id,
                        updated_at=excluded.updated_at
                    """,
                    (email, plan_id, session_id, now, now),
                )
                return True
        return False

    def get_entitlement(self, email: str | None) -> EntitlementResponse:
        self.initialize()
        normalized = normalize_email(email)
        if not normalized:
            return EntitlementResponse(email="", active=False, free_limit=FREE_ANALYSIS_LIMIT, free_used=0, free_remaining=FREE_ANALYSIS_LIMIT)

        with self._connect() as connection:
            entitlement_row = connection.execute(
                "SELECT email, plan_id, active FROM billing_entitlements WHERE email = ?",
                (normalized,),
            ).fetchone()
            usage_row = connection.execute(
                "SELECT used_count FROM ai_usage WHERE email = ?",
                (normalized,),
            ).fetchone()

        used = int(usage_row["used_count"]) if usage_row else 0
        remaining = max(FREE_ANALYSIS_LIMIT - used, 0)
        if not entitlement_row:
            return EntitlementResponse(
                email=normalized,
                active=False,
                free_limit=FREE_ANALYSIS_LIMIT,
                free_used=used,
                free_remaining=remaining,
            )
        return EntitlementResponse(
            email=entitlement_row["email"],
            plan_id=entitlement_row["plan_id"],
            active=bool(entitlement_row["active"]),
            free_limit=FREE_ANALYSIS_LIMIT,
            free_used=used,
            free_remaining=remaining,
        )

    def increment_ai_usage(self, email: str) -> int:
        self.initialize()
        normalized = normalize_email(email)
        if not normalized:
            raise HTTPException(status_code=400, detail="请先填写邮箱，用于记录免费 AI 总结次数。")
        now = utc_now()
        with _lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ai_usage (email, used_count, created_at, updated_at)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    used_count=used_count + 1,
                    updated_at=excluded.updated_at
                """,
                (normalized, now, now),
            )
            row = connection.execute("SELECT used_count FROM ai_usage WHERE email = ?", (normalized,)).fetchone()
        return int(row["used_count"]) if row else 0


class BillingService:
    def __init__(self, store: BillingStore | None = None) -> None:
        self.store = store or BillingStore()

    def create_checkout(self, email: str, plan_id: str = PRO_PLAN_ID) -> CheckoutResponse:
        if plan_id != PRO_PLAN_ID:
            raise HTTPException(status_code=400, detail="当前仅支持开通 Pro 权益。")

        normalized_email = normalize_email(email)
        if self.entitlement_for_email(normalized_email).active:
            raise HTTPException(status_code=409, detail="该账号已经是 Pro 会员，无需重复开通。")

        settings = get_settings()
        if not settings.stripe_secret_key:
            raise HTTPException(status_code=503, detail="请先配置 STRIPE_SECRET_KEY 后再创建支付。")

        try:
            import stripe
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="后端缺少 stripe 依赖，请先安装 requirements.txt。") from exc

        params = {
            "customer_email": normalized_email,
            "line_items": [
                {
                    "price_data": {
                        "currency": settings.stripe_price_currency,
                        "unit_amount": settings.stripe_price_amount,
                        "product_data": {
                            "name": settings.stripe_product_name,
                            "description": "一次性开通无限 AI 视频总结、AI 问答、字幕整理和思维导图能力。",
                        },
                    },
                    "quantity": 1,
                }
            ],
            "mode": "payment",
            "success_url": f"{settings.app_public_url}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{settings.app_public_url}/?checkout=cancel",
            "metadata": {"plan_id": plan_id, "email": normalized_email},
        }

        try:
            client = stripe.StripeClient(settings.stripe_secret_key)
            session = client.v1.checkout.sessions.create(params=params)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Stripe Checkout 创建失败：{exc}") from exc

        session_dict = self._stripe_object_to_dict(session)
        checkout_url = str(session_dict.get("url") or "")
        session_id = str(session_dict.get("id") or "")
        if not checkout_url or not session_id:
            raise HTTPException(status_code=502, detail="Stripe 未返回可用的支付链接。")

        self.store.record_checkout_session(session_dict, normalized_email, plan_id)
        return CheckoutResponse(checkout_url=checkout_url, session_id=session_id)

    def construct_webhook_event(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        settings = get_settings()
        if not settings.stripe_webhook_secret:
            raise HTTPException(status_code=503, detail="请先配置 STRIPE_WEBHOOK_SECRET 后再接收回调。")
        if not signature:
            raise HTTPException(status_code=400, detail="缺少 Stripe-Signature 请求头。")

        try:
            import stripe
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="后端缺少 stripe 依赖，请先安装 requirements.txt。") from exc

        try:
            client = stripe.StripeClient(settings.stripe_secret_key or "sk_test_placeholder")
            if hasattr(client, "construct_event"):
                event = client.construct_event(payload, signature, settings.stripe_webhook_secret)
            else:
                event = stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Stripe webhook payload 不是有效 JSON。") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Stripe webhook 签名验证失败。") from exc

        return self._stripe_object_to_dict(event)

    def handle_webhook_event(self, event: dict[str, Any]) -> dict[str, bool | str]:
        event_type = str(event.get("type") or "")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        session = data.get("object") if isinstance(data.get("object"), dict) else {}

        if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
            fulfilled = self.store.fulfill_checkout_session(session, str(event.get("id") or ""))
            return {"received": True, "fulfilled": fulfilled}

        if event_type == "checkout.session.async_payment_failed":
            self.store.fulfill_checkout_session({**session, "payment_status": "failed"}, str(event.get("id") or ""))
            return {"received": True, "fulfilled": False}

        return {"received": True, "fulfilled": False}

    def entitlement_for_email(self, email: str | None) -> EntitlementResponse:
        return self.store.get_entitlement(email)

    def ensure_ai_analysis_allowed(self, email: str | None) -> EntitlementResponse:
        entitlement = self.entitlement_for_email(email)
        if entitlement.active:
            return entitlement
        if not entitlement.email:
            raise HTTPException(status_code=402, detail="请先填写邮箱，免费版可体验 3 次 AI 视频总结。")
        if entitlement.free_remaining <= 0:
            raise HTTPException(status_code=402, detail="免费 AI 总结次数已用完，请开通 Pro 后无限使用。")
        return entitlement

    def record_ai_analysis_success(self, email: str | None) -> EntitlementResponse:
        entitlement = self.entitlement_for_email(email)
        if entitlement.active:
            return entitlement
        normalized = normalize_email(email)
        self.store.increment_ai_usage(normalized)
        return self.entitlement_for_email(normalized)

    def ensure_ai_chat_allowed(self, email: str | None) -> EntitlementResponse:
        entitlement = self.entitlement_for_email(email)
        if entitlement.active or entitlement.free_used > 0:
            return entitlement
        raise HTTPException(status_code=402, detail="请先生成一次 AI 视频总结，或开通 Pro 使用 AI 问答。")

    def require_pro_entitlement(self, email: str | None) -> None:
        entitlement = self.entitlement_for_email(email)
        if not entitlement.active:
            raise HTTPException(status_code=402, detail="AI 总结是 Pro 权益，请先用邮箱开通后再使用。")

    def _stripe_object_to_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "to_dict_recursive"):
            return value.to_dict_recursive()
        if hasattr(value, "to_dict"):
            return value.to_dict()
        return dict(value)


billing_service = BillingService()
