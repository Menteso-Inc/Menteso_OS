from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Article
from ..queue import enqueue_job
from ..schemas import JobRequestIn

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("")
def list_articles(db: Session = Depends(get_db)):
    rows = db.query(Article).order_by(Article.updated_at.desc()).all()
    return [
        {
            "id": f"article-{row.id}",
            "title": row.title,
            "primaryKeyword": row.primary_keyword,
            "status": row.status,
            "seoScore": row.seo_score,
            "readabilityScore": row.readability_score,
            "updatedAt": row.updated_at,
            "authoringMode": row.metadata_json.get("authoringMode", "AI + optimization"),
        }
        for row in rows
    ]


@router.post("/generate")
def generate_article(request: JobRequestIn):
    return enqueue_job("article-generation", request.input_ref, request.payload)

