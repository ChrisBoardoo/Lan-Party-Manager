import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Sponsor, LanEvent, User
from schemas import SponsorCreate, SponsorUpdate, SponsorOut
from auth import require_admin
from activity import add_activity
from event_utils import current_event
from file_validation import matches_declared
from router_settings import require_feature
from uploads import UPLOAD_DIR, read_capped, remove_upload

router = APIRouter()

# Banners are stored as-is (no re-encoding) so animated GIF/WebM keep moving.
_BANNER_MIME_TO_EXT = {
    "image/png": ("png", "image"),
    "image/gif": ("gif", "image"),
    "video/webm": ("webm", "video"),
}
MAX_BANNER_SIZE = 20 * 1024 * 1024  # 20 MB


def _list_for_event(db: Session, event_id: int):
    return (
        db.query(Sponsor)
        .filter(Sponsor.event_id == event_id)
        .order_by(Sponsor.sort_order, Sponsor.id)
        .all()
    )


@router.get("/", response_model=list[SponsorOut])
def list_sponsors(
    event_id: int = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("sponsors")),
):
    return _list_for_event(db, event_id)


@router.get("/active", response_model=list[SponsorOut])
def list_active_sponsors(
    db: Session = Depends(get_db),
    _: User = Depends(require_feature("sponsors")),
):
    """Sponsors of the current event — used on pages that aren't tied to a
    specific event (Tournaments list, player profiles)."""
    event = current_event(db)
    if not event:
        return []
    return _list_for_event(db, event.id)


@router.post("/", response_model=SponsorOut)
def create_sponsor(
    data: SponsorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not db.query(LanEvent).filter(LanEvent.id == data.event_id).first():
        raise HTTPException(404, "Event not found")
    sponsor = Sponsor(event_id=data.event_id, name=data.name, link_url=data.link_url)
    db.add(sponsor)
    db.commit()
    db.refresh(sponsor)
    add_activity(db, current_user.id, "sponsor_added", f"Added sponsor: {sponsor.name}", "sponsor", sponsor.id)
    db.commit()
    return sponsor


@router.post("/{sponsor_id}/banner", response_model=SponsorOut)
async def upload_sponsor_banner(
    sponsor_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    sponsor = db.query(Sponsor).filter(Sponsor.id == sponsor_id).first()
    if not sponsor:
        raise HTTPException(404, "Sponsor not found")
    if file.content_type not in _BANNER_MIME_TO_EXT:
        raise HTTPException(400, "Unsupported file type. Allowed: PNG, GIF, WebM.")

    # Capped while reading, not after: `await file.read()` then a length check
    # still buffers a 100 MB banner whole before refusing it.
    content = await read_capped(file, MAX_BANNER_SIZE)

    # Don't trust the client-declared content_type — verify the real bytes match.
    if not matches_declared(content, file.content_type):
        raise HTTPException(400, "File content does not match its declared type.")

    ext, banner_type = _BANNER_MIME_TO_EXT[file.content_type]
    filename = f"sponsor_{sponsor_id}_{uuid.uuid4().hex}.{ext}"
    sponsor_dir = os.path.join(UPLOAD_DIR, "sponsors")
    os.makedirs(sponsor_dir, exist_ok=True)
    with open(os.path.join(sponsor_dir, filename), "wb") as f:
        f.write(content)

    remove_upload(sponsor.banner_url, "sponsors")
    sponsor.banner_url = f"/uploads/sponsors/{filename}"
    sponsor.banner_type = banner_type
    db.commit()
    db.refresh(sponsor)
    return sponsor


@router.put("/{sponsor_id}", response_model=SponsorOut)
def update_sponsor(
    sponsor_id: int,
    data: SponsorUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    sponsor = db.query(Sponsor).filter(Sponsor.id == sponsor_id).first()
    if not sponsor:
        raise HTTPException(404, "Sponsor not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(sponsor, field, value)
    db.commit()
    db.refresh(sponsor)
    return sponsor


@router.delete("/{sponsor_id}")
def delete_sponsor(
    sponsor_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    sponsor = db.query(Sponsor).filter(Sponsor.id == sponsor_id).first()
    if not sponsor:
        raise HTTPException(404, "Sponsor not found")
    remove_upload(sponsor.banner_url, "sponsors")
    db.delete(sponsor)
    db.commit()
    return {"ok": True}

