from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Setting
from ..schemas import SettingUpsertIn

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def list_settings(db: Session = Depends(get_db)):
    rows = db.query(Setting).order_by(Setting.key.asc()).all()
    return [
        {
            "key": row.key,
            "value": {"configured": True} if row.is_secret else row.value,
            "isSecret": row.is_secret,
        }
        for row in rows
    ]


@router.post("")
def upsert_setting(payload: SettingUpsertIn, db: Session = Depends(get_db)):
    row = db.query(Setting).filter(Setting.key == payload.key).first()
    if not row:
        row = Setting(key=payload.key, value=payload.value, is_secret=payload.is_secret)
        db.add(row)
    else:
        row.value = payload.value
        row.is_secret = payload.is_secret
    db.commit()
    return {"status": "saved", "key": payload.key}
