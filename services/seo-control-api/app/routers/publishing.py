from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PublishingJob
from ..queue import enqueue_job
from ..schemas import JobRequestIn

router = APIRouter(prefix="/api/publishing", tags=["publishing"])


@router.get("/logs")
def publishing_logs(db: Session = Depends(get_db)):
    rows = db.query(PublishingJob).order_by(PublishingJob.created_at.desc()).all()
    return [
        {
            "id": f"publishing-{row.id}",
            "articleTitle": f"Publishing job #{row.id}",
            "destination": row.destination,
            "status": row.status,
            "createdAt": row.created_at,
            "detail": row.detail,
        }
        for row in rows
    ]


@router.post("/publish")
def publish_article(request: JobRequestIn):
    return enqueue_job("publishing", request.input_ref, request.payload)

