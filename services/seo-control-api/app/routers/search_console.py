from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import SearchConsoleSnapshot
from ..queue import enqueue_job
from ..schemas import JobRequestIn

router = APIRouter(prefix="/api/search-console", tags=["search-console"])


@router.get("/snapshots")
def snapshots(db: Session = Depends(get_db)):
    rows = db.query(SearchConsoleSnapshot).order_by(SearchConsoleSnapshot.captured_at.desc()).all()
    return [
        {
            "id": f"snapshot-{row.id}",
            "url": row.url,
            "impressions": row.impressions,
            "clicks": row.clicks,
            "ctr": row.ctr,
            "averagePosition": row.average_position,
            "capturedAt": row.captured_at,
        }
        for row in rows
    ]


@router.post("/index")
def request_indexing(request: JobRequestIn):
    return enqueue_job("indexing", request.input_ref, request.payload)

