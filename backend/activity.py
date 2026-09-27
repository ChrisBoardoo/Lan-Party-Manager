from sqlalchemy.orm import Session
from models import ActivityLog, AuditLog


def add_activity(
    db: Session,
    user_id: int,
    action: str,
    description: str,
    entity_type: str = None,
    entity_id: int = None,
    recipient_user_id: int = None,
):
    db.add(ActivityLog(
        user_id=user_id,
        action=action,
        description=description,
        entity_type=entity_type,
        entity_id=entity_id,
        recipient_user_id=recipient_user_id,
    ))


def add_audit(db: Session, admin_id: int, action: str, details: str = None):
    db.add(AuditLog(admin_id=admin_id, action=action, details=details))
