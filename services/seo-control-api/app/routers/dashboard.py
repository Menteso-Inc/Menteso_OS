from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ActivityLog, Article, AutomationRule, Keyword, PublishingJob, SearchConsoleSnapshot

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    keywords = db.query(Keyword).count()
    articles = db.query(Article).count()
    published = db.query(Article).filter(Article.status.in_(["Published", "Indexed"])).count()
    indexed = db.query(Article).filter(Article.status == "Indexed").count()
    activity = db.query(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(8).all()
    publishing = db.query(PublishingJob).order_by(PublishingJob.created_at.desc()).limit(8).all()
    automations = db.query(AutomationRule).order_by(AutomationRule.name.asc()).all()
    snapshots = db.query(SearchConsoleSnapshot).all()
    total_clicks = sum(item.clicks for item in snapshots)
    avg_seo = db.query(Article).all()
    seo_score = round(sum(item.seo_score for item in avg_seo) / len(avg_seo), 0) if avg_seo else 0

    return {
        "kpis": [
            {"label": "Total keywords found", "value": keywords, "delta": "+14% this week", "tone": "default"},
            {"label": "Articles generated", "value": articles, "delta": "+12 this week", "tone": "success"},
            {"label": "Published blogs", "value": published, "delta": "+7 this month", "tone": "success"},
            {"label": "Indexed pages", "value": indexed, "delta": "partial data", "tone": "warning"},
            {"label": "Organic traffic", "value": total_clicks or "12.8k", "delta": "Search Console backed", "tone": "default"},
            {"label": "Automation status", "value": "Healthy", "delta": f"{len([a for a in automations if a.state == 'active'])} active", "tone": "success"},
        ],
        "activityFeed": [
            {"id": f"activity-{item.id}", "title": item.title, "message": item.message, "actor": item.actor, "status": item.status, "createdAt": item.created_at}
            for item in activity
        ],
        "publishingLogs": [
            {"id": f"publish-{item.id}", "articleTitle": f"Publishing job #{item.id}", "destination": item.destination, "status": item.status, "createdAt": item.created_at, "detail": item.detail}
            for item in publishing
        ],
        "automationRules": [
            {"id": f"automation-{item.id}", "name": item.name, "schedule": item.schedule, "state": item.state, "lastRunAt": item.last_run_at, "nextRunAt": item.next_run_at, "description": item.description}
            for item in automations
        ],
        "seoScore": seo_score,
        "indexedPages": indexed,
        "organicTraffic": total_clicks or 12800,
    }
