from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Keyword
from ..queue import enqueue_job
from ..schemas import JobRequestIn

router = APIRouter(prefix="/api/keywords", tags=["keywords"])


@router.get("")
def list_keywords(db: Session = Depends(get_db)):
    rows = db.query(Keyword).order_by(Keyword.created_at.desc()).all()
    return [
        {
            "id": f"keyword-{row.id}",
            "keyword": row.keyword,
            "cluster": row.cluster,
            "intent": row.intent,
            "volume": row.volume,
            "difficulty": row.difficulty,
            "cpc": row.cpc,
            "trend": row.trend,
            "competitionTier": row.competition_tier,
            "status": row.status,
        }
        for row in rows
    ]


@router.post("/discover")
def discover_keywords(request: JobRequestIn):
    return enqueue_job("keyword-research", request.input_ref, request.payload)

