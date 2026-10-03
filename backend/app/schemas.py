"""Pydantic request/response models (API contract, kept separate from ORM models)."""
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, EmailStr


# --- Auth ---
class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


# --- Google Ads Accounts ---
class AccountResponse(BaseModel):
    id: str
    customer_id: str
    descriptive_name: Optional[str]
    notify_email: str
    dry_run: bool
    max_actions_per_run: int
    is_active: bool
    connected_at: datetime
    last_run_at: Optional[datetime]

    class Config:
        from_attributes = True


class AccountSettingsUpdate(BaseModel):
    notify_email: Optional[EmailStr] = None
    dry_run: Optional[bool] = None
    max_actions_per_run: Optional[int] = None
    is_active: Optional[bool] = None


# --- Audit log ---
class AuditEntryResponse(BaseModel):
    id: str
    timestamp: datetime
    action: str
    params: dict[str, Any]
    reason: str
    dry_run: bool
    success: bool
    error: Optional[str]

    class Config:
        from_attributes = True


# --- Recommendations ---
class RecommendationResponse(BaseModel):
    id: str
    kind: str
    campaign_id: str
    campaign_name: str
    detail: str
    metrics: dict[str, Any]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class RecommendationStatusUpdate(BaseModel):
    status: str  # "dismissed" | "applied"
