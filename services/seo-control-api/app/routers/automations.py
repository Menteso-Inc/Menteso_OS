from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AutomationRule

router = APIRouter(prefix="/api/automations", tags=["automations"])


@router.get("")
def list_automations(db: Session = Depends(get_db)):
    rows = db.query(AutomationRule).order_by(AutomationRule.name.asc()).all()
    return [
        {
            "id": f"automation-{row.id}",
            "name": row.name,
            "schedule": row.schedule,
            "state": row.state,
            "lastRunAt": row.last_run_at,
            "nextRunAt": row.next_run_at,
            "description": row.description,
        }
        for row in rows
    ]

