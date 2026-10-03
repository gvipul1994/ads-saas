from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, AuditLogEntry
from app.schemas import AuditEntryResponse
from app.auth import get_current_user
from app.routers.accounts import _get_owned_account

router = APIRouter(prefix="/accounts/{account_id}/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntryResponse])
def list_audit_entries(account_id: str, limit: int = 100,
                        current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_account(account_id, current_user, db)
    return (db.query(AuditLogEntry)
            .filter(AuditLogEntry.account_id == account_id)
            .order_by(AuditLogEntry.timestamp.desc())
            .limit(limit)
            .all())
