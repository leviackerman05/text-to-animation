import json
import os
import re
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.models import (
    SignupRequest,
    LoginRequest,
    AuthResponse,
    ChatRequest,
    ChatResponse,
    MeResponse,
    CheckoutResponse,
)
from app.script_gen import generate_and_render, build_generation_prompt
from app.renderer import get_video_metadata
from app.video_storage import persist_video, resolve_local_stream_path
from app.supabase_client import supabase
from app.auth import verify_token
from app.chat_service import (
    create_chat,
    add_message,
    get_chat_history,
    get_user_chats,
    delete_chat,
    check_chat_exists,
    update_chat_title,
)
from app.profile_service import (
    check_can_generate,
    increment_usage,
    get_usage_info,
    get_user_plan,
    set_user_plan,
    get_stripe_customer_id,
)
from app import billing

app = FastAPI(title="Vizion API")


def _cors_origins() -> list[str]:
    origins: list[str] = []
    frontend = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    if frontend:
        origins.append(frontend)
    extra = os.getenv("CORS_ORIGINS", "")
    if extra:
        origins.extend(o.strip().rstrip("/") for o in extra.split(",") if o.strip())
    if os.getenv("ENV", "development") != "production":
        origins.extend([
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:5173",
        ])
    if not origins:
        origins = ["http://localhost:8080", "http://127.0.0.1:8080"]
    return list(dict.fromkeys(origins))


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


def _finalize_video(result, user_id: str, chat_id: str) -> tuple[str, dict]:
    """Upload to cloud storage and return a stream URL (not a direct file download)."""
    local_path = result.local_path
    if not local_path and result.video_url:
        rel = result.video_url.replace("/static/outputs/", "")
        local_path = os.path.join("app/static/outputs", rel)
    if local_path and os.path.exists(local_path):
        return persist_video(local_path, user_id, chat_id)
    return result.video_url or "", get_video_metadata(result.video_url or "")


@app.get("/videos/{video_id}/stream")
def stream_video(video_id: str):
    """Stream video inline in the browser — does not trigger a file download."""
    path = resolve_local_stream_path(video_id)
    if not path:
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(
        path,
        media_type="video/mp4",
        headers={"Content-Disposition": "inline", "Cache-Control": "no-cache"},
    )


@app.get("/videos/{video_id}/download")
def download_video(video_id: str, user: dict = Depends(verify_token)):
    """Download video only when the user explicitly requests it."""
    path = resolve_local_stream_path(video_id)
    if not path:
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename="vizion-animation.mp4",
        headers={"Content-Disposition": 'attachment; filename="vizion-animation.mp4"'},
    )


def _run_generation(prompt: str, hd: bool, status_events: list):
    def on_status(stage: str, message: str):
        status_events.append({"stage": stage, "message": message})

    script_code, result = generate_and_render(
        prompt,
        output_path="app/static/outputs/generated_scene.py",
        hd=hd,
        on_status=on_status,
    )
    return script_code, result


@app.post("/signup", response_model=AuthResponse)
def signup(request: SignupRequest):
    try:
        username = request.username or request.email.split("@")[0]
        response = supabase.auth.sign_up({
            "email": request.email,
            "password": request.password,
            "options": {"data": {"username": username}},
        })
        if response.user is None:
            raise HTTPException(status_code=400, detail="Signup failed")
        return {
            "access_token": "",
            "token_type": "bearer",
            "active_plan": "free",
            "user": {
                "id": response.user.id,
                "email": response.user.email,
                "username": response.user.user_metadata.get("username"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        detail = str(e)
        if "validation error" in detail.lower() or "Value error" in detail:
            raise HTTPException(status_code=400, detail=detail.split("\n")[-1].strip())
        raise HTTPException(status_code=400, detail=detail)


@app.post("/login", response_model=AuthResponse)
def login(request: LoginRequest):
    try:
        response = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password,
        })
        if response.user is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        plan = get_user_plan(response.user.id)
        return {
            "access_token": response.session.access_token,
            "token_type": "bearer",
            "active_plan": plan,
            "user": {
                "id": response.user.id,
                "email": response.user.email,
                "username": response.user.user_metadata.get("username"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.get("/me", response_model=MeResponse)
def get_me(user: dict = Depends(verify_token)):
    usage = get_usage_info(user["sub"])
    return MeResponse(
        user_id=user["sub"],
        email=user.get("email"),
        plan=usage["plan"],
        daily_count=usage["daily_count"],
        daily_limit=usage["daily_limit"],
        remaining=usage["remaining"],
    )


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest, user: dict = Depends(verify_token)):
    try:
        user_id = user["sub"]
        can_gen, limit_msg = check_can_generate(user_id)
        if not can_gen:
            raise HTTPException(status_code=402, detail=limit_msg)

        chat_id = request.chat_id
        prompt = request.prompt
        plan = get_user_plan(user_id)
        hd = plan == "pro"

        if not chat_id:
            title = (prompt[:30] + "...") if len(prompt) > 30 else prompt
            chat_id = create_chat(user_id, title)
        elif not check_chat_exists(chat_id):
            title = (prompt[:30] + "...") if len(prompt) > 30 else prompt
            chat_id = create_chat(user_id, title, chat_id=chat_id)

        add_message(chat_id, "user", prompt)

        history = get_chat_history(chat_id)
        generation_prompt = build_generation_prompt(prompt, history)

        script_code, result = generate_and_render(
            generation_prompt,
            output_path="app/static/outputs/generated_scene.py",
            hd=hd,
        )

        if not result.success:
            raise HTTPException(status_code=500, detail=result.error_log[:500])

        video_url, metadata = _finalize_video(result, user_id, chat_id)
        increment_usage(user_id)
        add_message(chat_id, "assistant", "Here is your video!", video_url)

        return {
            "chat_id": chat_id,
            "script": script_code,
            "metadata": metadata,
            "message": {
                "role": "assistant",
                "content": "Here is your video!",
                "video_url": video_url,
                "script": script_code,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
def chat_stream_endpoint(request: ChatRequest, user: dict = Depends(verify_token)):
    user_id = user["sub"]
    can_gen, limit_msg = check_can_generate(user_id)
    if not can_gen:
        raise HTTPException(status_code=402, detail=limit_msg)

    prompt = request.prompt
    chat_id = request.chat_id
    plan = get_user_plan(user_id)
    hd = plan == "pro"

    if not chat_id:
        title = (prompt[:30] + "...") if len(prompt) > 30 else prompt
        chat_id = create_chat(user_id, title)
    elif not check_chat_exists(chat_id):
        title = (prompt[:30] + "...") if len(prompt) > 30 else prompt
        chat_id = create_chat(user_id, title, chat_id=chat_id)

    add_message(chat_id, "user", prompt)

    history = get_chat_history(chat_id)
    generation_prompt = build_generation_prompt(prompt, history)

    def event_generator():
        status_events = []

        def on_status(stage: str, message: str):
            status_events.append({"stage": stage, "message": message})

        yield f"data: {json.dumps({'stage': 'analyzing', 'message': 'Analyzing your prompt...', 'chat_id': chat_id})}\n\n"

        script_code, result = generate_and_render(
            generation_prompt,
            output_path="app/static/outputs/generated_scene.py",
            hd=hd,
            on_status=on_status,
        )

        for evt in status_events:
            evt["chat_id"] = chat_id
            yield f"data: {json.dumps(evt)}\n\n"

        if not result.success:
            yield f"data: {json.dumps({'stage': 'error', 'message': result.error_log[:300], 'chat_id': chat_id})}\n\n"
            return

        video_url, metadata = _finalize_video(result, user_id, chat_id)
        increment_usage(user_id)
        add_message(chat_id, "assistant", "Here is your video!", video_url)

        yield f"data: {json.dumps({'stage': 'done', 'message': 'Video ready!', 'chat_id': chat_id, 'video_url': video_url, 'script': script_code, 'metadata': metadata})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/chats")
def list_chats(user: dict = Depends(verify_token)):
    try:
        return get_user_chats(user["sub"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chatdata/{chat_id}")
def get_chat_data(chat_id: str, user: dict = Depends(verify_token)):
    try:
        return get_chat_history(chat_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chats/{chat_id}")
def get_chat_by_id(chat_id: str, user: dict = Depends(verify_token)):
    return get_chat_data(chat_id, user)


@app.patch("/chats/{chat_id}")
def rename_chat(chat_id: str, request: dict, user: dict = Depends(verify_token)):
    title = request.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title required")
    update_chat_title(chat_id, title)
    return {"status": "success", "title": title}


@app.delete("/chats/{chat_id}")
def delete_chat_endpoint(chat_id: str, user: dict = Depends(verify_token)):
    try:
        delete_chat(chat_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/billing/create-checkout-session", response_model=CheckoutResponse)
def create_checkout(user: dict = Depends(verify_token)):
    try:
        url = billing.create_checkout_session(user["sub"], user.get("email", ""))
        return {"url": url}
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/billing/portal", response_model=CheckoutResponse)
def billing_portal(user: dict = Depends(verify_token)):
    customer_id = get_stripe_customer_id(user["sub"])
    if not customer_id:
        raise HTTPException(status_code=400, detail="No billing account found")
    try:
        url = billing.create_portal_session(customer_id)
        return {"url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/billing/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = billing.construct_webhook_event(payload, sig)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("client_reference_id") or session.get("metadata", {}).get("user_id")
        customer_id = session.get("customer")
        if user_id:
            set_user_plan(user_id, "pro", stripe_customer_id=customer_id)

    return {"status": "ok"}


# CLI entry point
def cli_mode():
    import subprocess
    prompt = input("Enter your prompt: ")
    output_path = "app/static/outputs/generated_scene.py"
    script_code, result = generate_and_render(prompt, output_path=output_path)
    if not result.success:
        print("Failed:", result.error_log)
        return
    print("Video:", result.video_url)


if __name__ == "__main__":
    cli_mode()
