from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional

from app.email_validation import validate_signup_email


class GenerateRequest(BaseModel):
    prompt: str


class GenerateResponse(BaseModel):
    video_url: str
    script: Optional[str] = None


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    username: str = ""

    @field_validator("email")
    @classmethod
    def check_allowed_provider(cls, value: str) -> str:
        ok, message = validate_signup_email(value)
        if not ok:
            raise ValueError(message)
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def check_password_length(cls, value: str) -> str:
        if len(value) < 6:
            raise ValueError("Password must be at least 6 characters")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
    active_plan: str = "free"


class Message(BaseModel):
    role: str
    content: str
    video_url: Optional[str] = None
    script: Optional[str] = None


class ChatRequest(BaseModel):
    prompt: str
    chat_id: Optional[str] = None
    user_id: Optional[str] = None


class ChatResponse(BaseModel):
    chat_id: str
    message: Message
    script: Optional[str] = None
    metadata: Optional[dict] = None


class MeResponse(BaseModel):
    user_id: str
    email: Optional[str] = None
    plan: str
    daily_count: int
    daily_limit: Optional[int] = None
    remaining: Optional[int] = None


class CheckoutResponse(BaseModel):
    url: str
