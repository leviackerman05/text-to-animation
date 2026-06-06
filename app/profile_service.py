from datetime import date
from typing import Optional

from app.supabase_client import supabase, supabase_admin

FREE_DAILY_LIMIT = 5


def _client():
    return supabase_admin if supabase_admin else supabase


def get_or_create_profile(user_id: str) -> dict:
    client = _client()
    try:
        response = client.table("profiles").select("*").eq("user_id", user_id).execute()

        if response.data:
            profile = response.data[0]
        else:
            new_profile = {
                "user_id": user_id,
                "plan": "free",
                "daily_count": 0,
                "period_start": date.today().isoformat(),
            }
            insert = client.table("profiles").insert(new_profile).execute()
            profile = insert.data[0]

        return _reset_period_if_needed(profile)
    except Exception as e:
        print(f"Profile table unavailable ({e}), using defaults")
        return {
            "user_id": user_id,
            "plan": "free",
            "daily_count": 0,
            "period_start": date.today().isoformat(),
        }


def _reset_period_if_needed(profile: dict) -> dict:
    today = date.today().isoformat()
    if profile.get("period_start") != today:
        client = _client()
        updated = (
            client.table("profiles")
            .update({"daily_count": 0, "period_start": today})
            .eq("user_id", profile["user_id"])
            .execute()
        )
        return updated.data[0] if updated.data else profile
    return profile


def get_user_plan(user_id: str) -> str:
    return get_or_create_profile(user_id).get("plan", "free")


def get_usage_info(user_id: str) -> dict:
    profile = get_or_create_profile(user_id)
    plan = profile.get("plan", "free")
    daily_count = profile.get("daily_count", 0)
    limit = None if plan == "pro" else FREE_DAILY_LIMIT
    remaining = None if plan == "pro" else max(0, FREE_DAILY_LIMIT - daily_count)
    return {
        "plan": plan,
        "daily_count": daily_count,
        "daily_limit": limit,
        "remaining": remaining,
    }


def check_can_generate(user_id: str) -> tuple[bool, str]:
    info = get_usage_info(user_id)
    if info["plan"] == "pro":
        return True, ""
    if info["daily_count"] >= FREE_DAILY_LIMIT:
        return False, f"Daily limit reached ({FREE_DAILY_LIMIT} videos). Upgrade to Pro for unlimited."
    return True, ""


def increment_usage(user_id: str) -> None:
    profile = get_or_create_profile(user_id)
    if profile.get("plan") == "pro":
        return
    try:
        client = _client()
        client.table("profiles").update(
            {"daily_count": profile.get("daily_count", 0) + 1}
        ).eq("user_id", user_id).execute()
    except Exception:
        pass


def set_user_plan(user_id: str, plan: str, stripe_customer_id: Optional[str] = None) -> dict:
    client = _client()
    update_data = {"plan": plan, "updated_at": date.today().isoformat()}
    if stripe_customer_id:
        update_data["stripe_customer_id"] = stripe_customer_id
    response = client.table("profiles").update(update_data).eq("user_id", user_id).execute()
    return response.data[0] if response.data else {}


def get_stripe_customer_id(user_id: str) -> Optional[str]:
    profile = get_or_create_profile(user_id)
    return profile.get("stripe_customer_id")
