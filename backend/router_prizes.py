from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Prize, LanEvent, User
from schemas import PrizeCreate, PrizeUpdate, PrizeOut
from auth import require_admin
from activity import add_activity
from router_settings import require_feature
from uploads import remove_upload, save_image_upload

router = APIRouter()


@router.get("/", response_model=list[PrizeOut])
def list_prizes(
    event_id: int = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("prizes")),
):
    return (
        db.query(Prize)
        .filter(Prize.event_id == event_id)
        .order_by(Prize.sort_order, Prize.id)
        .all()
    )


@router.post("/", response_model=PrizeOut)
def create_prize(
    data: PrizeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not db.query(LanEvent).filter(LanEvent.id == data.event_id).first():
        raise HTTPException(404, "Event not found")
    prize = Prize(event_id=data.event_id, title=data.title, description=data.description)
    db.add(prize)
    db.commit()
    db.refresh(prize)
    add_activity(db, current_user.id, "prize_added", f"Added prize: {prize.title}", "prize", prize.id)
    db.commit()
    return prize


@router.post("/{prize_id}/photo", response_model=PrizeOut)
async def upload_prize_photo(
    prize_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    prize = db.query(Prize).filter(Prize.id == prize_id).first()
    if not prize:
        raise HTTPException(404, "Prize not found")

    prize.photo_url = await save_image_upload(
        file, subdir="prizes", prefix=f"prize_{prize_id}", box=(1000, 1000), quality=82,
        replaces=prize.photo_url,
    )
    db.commit()
    db.refresh(prize)
    return prize


@router.put("/{prize_id}", response_model=PrizeOut)
def update_prize(
    prize_id: int,
    data: PrizeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    prize = db.query(Prize).filter(Prize.id == prize_id).first()
    if not prize:
        raise HTTPException(404, "Prize not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(prize, field, value)
    db.commit()
    db.refresh(prize)
    return prize


@router.delete("/{prize_id}")
def delete_prize(
    prize_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    prize = db.query(Prize).filter(Prize.id == prize_id).first()
    if not prize:
        raise HTTPException(404, "Prize not found")
    remove_upload(prize.photo_url, "prizes")
    db.delete(prize)
    db.commit()
    return {"ok": True}
