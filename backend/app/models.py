"""
SQLAlchemy models.

One user can connect multiple Google Ads accounts (e.g. an agency owner
managing several clients under their own login), and each account carries
its own encrypted refresh token, its own safety settings, and its own
audit/recommendation history.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Boolean, Integer, DateTime, ForeignKey, Text, JSON, Enum, Float
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    accounts = relationship("GoogleAdsAccount", back_populates="owner", cascade="all, delete-orphan")


class GoogleAdsAccount(Base):
    __tablename__ = "google_ads_accounts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    owner_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)

    customer_id = Column(String, nullable=False)       # Google Ads customer id, digits only
    descriptive_name = Column(String, nullable=True)   # account name, pulled after connecting

    # Encrypted at rest - see core/crypto.py. Never returned by any API response.
    encrypted_refresh_token = Column(Text, nullable=False)

    notify_email = Column(String, nullable=False)       # where recommendations/reports go for THIS account
    dry_run = Column(Boolean, default=True, nullable=False)
    max_actions_per_run = Column(Integer, default=25, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)  # pause all automation for this account

    connected_at = Column(DateTime(timezone=True), default=_now)
    last_run_at = Column(DateTime(timezone=True), nullable=True)

    owner = relationship("User", back_populates="accounts")
    audit_entries = relationship("AuditLogEntry", back_populates="account", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="account", cascade="all, delete-orphan")


class PendingOAuthToken(Base):
    """
    Short-lived holding spot between the OAuth callback (where we get a
    refresh token and the list of Google Ads accounts it can access) and
    the user picking which account(s) to actually connect. Deleted as soon
    as it's used, and should be garbage-collected if abandoned (see
    core/scheduler.py cleanup job).
    """
    __tablename__ = "pending_oauth_tokens"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    encrypted_refresh_token = Column(Text, nullable=False)
    accessible_customer_ids = Column(JSON, nullable=False)  # list[str], from ListAccessibleCustomers
    created_at = Column(DateTime(timezone=True), default=_now)


class AuditLogEntry(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    account_id = Column(UUID(as_uuid=False), ForeignKey("google_ads_accounts.id"), nullable=False)

    timestamp = Column(DateTime(timezone=True), default=_now, index=True)
    action = Column(String, nullable=False)       # e.g. "mutate_ad_group_criterion_negative"
    params = Column(JSON, nullable=False)
    reason = Column(Text, nullable=False)
    result = Column(JSON, nullable=True)
    dry_run = Column(Boolean, nullable=False)
    success = Column(Boolean, default=True, nullable=False)
    error = Column(Text, nullable=True)

    account = relationship("GoogleAdsAccount", back_populates="audit_entries")


class RecommendationKind(str, enum.Enum):
    budget = "budget"
    bid = "bid"


class RecommendationStatus(str, enum.Enum):
    open = "open"
    dismissed = "dismissed"
    applied = "applied"  # client marks it applied after doing it themselves in Google Ads


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    account_id = Column(UUID(as_uuid=False), ForeignKey("google_ads_accounts.id"), nullable=False)

    kind = Column(Enum(RecommendationKind), nullable=False)
    campaign_id = Column(String, nullable=False)
    campaign_name = Column(String, nullable=False)
    detail = Column(Text, nullable=False)
    metrics = Column(JSON, nullable=False, default=dict)
    status = Column(Enum(RecommendationStatus), default=RecommendationStatus.open, nullable=False)

    created_at = Column(DateTime(timezone=True), default=_now)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    account = relationship("GoogleAdsAccount", back_populates="recommendations")
