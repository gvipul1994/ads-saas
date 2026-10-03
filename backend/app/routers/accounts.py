from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, GoogleAdsAccount
from app.schemas import AccountResponse, AccountSettingsUpdate
from app.auth import get_current_user
from app.core.run_account import run_account

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _get_owned_account(account_id: str, user: User, db: Session) -> GoogleAdsAccount:
    account = db.query(GoogleAdsAccount).filter(
        GoogleAdsAccount.id == account_id, GoogleAdsAccount.owner_id == user.id
    ).first()
    if not account:
        raise HTTPException(404, "Account not found")
    return account


@router.get("", response_model=list[AccountResponse])
def list_accounts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(GoogleAdsAccount).filter(GoogleAdsAccount.owner_id == current_user.id).all()


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_owned_account(account_id, current_user, db)


@router.patch("/{account_id}", response_model=AccountResponse)
def update_account_settings(account_id: str, body: AccountSettingsUpdate,
                             current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = _get_owned_account(account_id, current_user, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    return account


@router.post("/{account_id}/run-now")
def run_now(account_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Manually trigger one optimizer run for this account, outside the daily
    schedule. Respects the account's own dry_run setting — this does NOT
    force a live run if dry_run is on."""
    account = _get_owned_account(account_id, current_user, db)
    result = run_account(db, account)
    return result


@router.delete("/{account_id}")
def disconnect_account(account_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = _get_owned_account(account_id, current_user, db)
    db.delete(account)
    db.commit()
    return {"status": "disconnected"}
