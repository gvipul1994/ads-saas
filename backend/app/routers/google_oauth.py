"""
Per-client Google Ads OAuth connect flow.

Flow:
  1. GET /oauth/google/start   (authenticated) -> redirect to Google consent screen
  2. User approves on Google's site
  3. GET /oauth/google/callback -> exchange code for refresh_token, list
     accessible Google Ads customer ids, stash them in PendingOAuthToken,
     redirect to the frontend's "pick an account" screen
  4. POST /oauth/google/finalize -> frontend posts chosen customer_id(s);
     backend creates GoogleAdsAccount row(s) and deletes the pending record
"""
import httpx
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.auth import get_current_user, ALGORITHM
from app.models import User, PendingOAuthToken, GoogleAdsAccount
from app.core.crypto import encrypt_token, decrypt_token
from app.core.google_ads_client import GoogleAdsAccountClient

router = APIRouter(prefix="/oauth/google", tags=["google-oauth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/adwords"


def _state_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    return jwt.encode({"sub": user_id, "exp": expire, "purpose": "oauth_state"},
                       settings.secret_key, algorithm=ALGORITHM)


def _verify_state(state: str) -> str:
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get("purpose") != "oauth_state":
            raise HTTPException(400, "Invalid state")
        return payload["sub"]
    except JWTError:
        raise HTTPException(400, "Invalid or expired state")


@router.get("/start")
def start(current_user: User = Depends(get_current_user)):
    """
    Returns the Google consent URL as JSON (rather than redirecting directly)
    because this call must be authenticated with our own JWT, which a plain
    browser navigation can't carry in a header. The frontend calls this via
    axios (JWT attached automatically) then does the actual page redirect
    itself with the returned URL.
    """
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",   # forces a refresh_token even on repeat connects
        "state": _state_token(current_user.id),
    }
    return {"auth_url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}"}


@router.get("/callback")
def callback(code: str, state: str, db: Session = Depends(get_db)):
    user_id = _verify_state(state)

    with httpx.Client() as http:
        token_resp = http.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "grant_type": "authorization_code",
        })
    if token_resp.status_code != 200:
        raise HTTPException(400, f"Google token exchange failed: {token_resp.text}")

    tokens = token_resp.json()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        # Happens if the user previously connected without revoking access first;
        # Google only issues a refresh_token on the FIRST consent (prompt=consent
        # above should prevent this, but handle it defensively).
        raise HTTPException(
            400,
            "Google did not return a refresh token. Revoke this app's access at "
            "https://myaccount.google.com/permissions and try connecting again.",
        )

    try:
        customer_ids = GoogleAdsAccountClient.list_accessible_customers(refresh_token)
    except Exception as e:
        raise HTTPException(400, f"Connected to Google, but couldn't list Ads accounts: {e}")

    pending = PendingOAuthToken(
        user_id=user_id,
        encrypted_refresh_token=encrypt_token(refresh_token),
        accessible_customer_ids=customer_ids,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)

    return RedirectResponse(f"{settings.frontend_url}/connect/select?pending_id={pending.id}")


@router.get("/pending/{pending_id}")
def get_pending(pending_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pending = db.query(PendingOAuthToken).filter(
        PendingOAuthToken.id == pending_id, PendingOAuthToken.user_id == current_user.id
    ).first()
    if not pending:
        raise HTTPException(404, "Pending connection not found or expired")
    return {"pending_id": pending.id, "customer_ids": pending.accessible_customer_ids}


@router.post("/finalize")
def finalize(pending_id: str, customer_id: str, notify_email: str,
             current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pending = db.query(PendingOAuthToken).filter(
        PendingOAuthToken.id == pending_id, PendingOAuthToken.user_id == current_user.id
    ).first()
    if not pending:
        raise HTTPException(404, "Pending connection not found or expired")
    if customer_id not in pending.accessible_customer_ids:
        raise HTTPException(400, "That customer_id wasn't in the accounts this login can access")

    existing = db.query(GoogleAdsAccount).filter(
        GoogleAdsAccount.owner_id == current_user.id, GoogleAdsAccount.customer_id == customer_id
    ).first()
    if existing:
        raise HTTPException(400, "This Google Ads account is already connected")

    account = GoogleAdsAccount(
        owner_id=current_user.id,
        customer_id=customer_id,
        encrypted_refresh_token=pending.encrypted_refresh_token,
        notify_email=notify_email,
        dry_run=settings.default_dry_run,
        max_actions_per_run=settings.default_max_actions_per_run,
    )
    db.add(account)
    db.delete(pending)
    db.commit()
    db.refresh(account)

    return {"account_id": account.id, "customer_id": account.customer_id}
