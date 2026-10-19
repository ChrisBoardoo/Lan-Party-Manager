"""Monthly contract endpoint — /api/quests. The rules live in quests.py."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import quests
from auth import get_current_user
from database import get_db
from models import User
from router_settings import is_feature_enabled
from schemas import QuestContractOut

router = APIRouter()


@router.get("/current", response_model=QuestContractOut)
def current(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """This month's contract and my progress. The first look of the month
    draws it. 404 while the feature is off, admins included: a contract drawn
    while it's off would pay out the day it's switched on."""
    if not is_feature_enabled(db, "quests"):
        raise HTTPException(404, "This feature is not enabled")
    for attempt in range(2):
        try:
            contract = quests.current_contract(db)
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if attempt:
                raise
    return quests.contract_view(db, contract, user.id)
