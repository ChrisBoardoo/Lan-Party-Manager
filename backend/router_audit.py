from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models import AuditLog, User
from schemas import AuditLogOut
from auth import require_admin

router = APIRouter()


@router.get("/", response_model=list[AuditLogOut])
def list_audit(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return (
        db.query(AuditLog)
        .options(selectinload(AuditLog.admin))
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
