from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database import get_db
from app.models import User, Recommendation, RecommendationStatus
from app.schemas import RecommendationResponse, RecommendationStatusUpdate
from app.auth import get_current_user
from app.routers.accounts import _get_owned_account

router = APIRouter(prefix="/accounts/{account_id}/recommendations", tags=["recommendations"])


@router.get("", response_model=list[RecommendationResponse])
def list_recommendations(account_id: str, status: str | None = None,
                          current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_account(account_id, current_user, db)  # ownership check
    q = db.query(Recommendation).filter(Recommendation.account_id == account_id)
    if status:
        q = q.filter(Recommendation.status == status)
    return q.order_by(Recommendation.created_at.desc()).all()


@router.patch("/{rec_id}", response_model=RecommendationResponse)
def update_recommendation(account_id: str, rec_id: str, body: RecommendationStatusUpdate,
                           current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_owned_account(account_id, current_user, db)
    rec = db.query(Recommendation).filter(Recommendation.id == rec_id, Recommendation.account_id == account_id).first()
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    if body.status not in (RecommendationStatus.dismissed.value, RecommendationStatus.applied.value):
        raise HTTPException(400, "status must be 'dismissed' or 'applied'")
    rec.status = body.status
    rec.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rec)
    return rec
