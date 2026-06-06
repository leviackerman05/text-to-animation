import os

import stripe
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8080")


def is_configured() -> bool:
    return bool(stripe.api_key and STRIPE_PRICE_ID)


def create_checkout_session(user_id: str, email: str) -> str:
    if not is_configured():
        raise ValueError("Stripe is not configured. Set STRIPE_SECRET_KEY and STRIPE_PRICE_ID in .env")

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        success_url=f"{FRONTEND_URL}/profile?checkout=success",
        cancel_url=f"{FRONTEND_URL}/profile?checkout=cancel",
        client_reference_id=user_id,
        customer_email=email,
        metadata={"user_id": user_id},
    )
    return session.url


def create_portal_session(stripe_customer_id: str) -> str:
    if not stripe.api_key:
        raise ValueError("Stripe is not configured")
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=f"{FRONTEND_URL}/profile",
    )
    return session.url


def construct_webhook_event(payload: bytes, sig_header: str):
    if not STRIPE_WEBHOOK_SECRET:
        raise ValueError("STRIPE_WEBHOOK_SECRET not set")
    return stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
