from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ActivityLog

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("")
def list_activity(db: Session = Depends(get_db)):
    rows = db.query(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(50).all()
    return [
        {
            "id": f"activity-{row.id}",
            "title": row.title,
            "message": row.message,
            "actor": row.actor,
            "status": row.status,
            "createdAt": row.created_at,
        }
        for row in rows
    ]

