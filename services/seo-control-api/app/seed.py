from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from .models import ActivityLog, Article, AutomationRule, Keyword, PublishingJob


def ensure_seed_data(db: Session):
    if db.query(Keyword).count() == 0:
        db.add_all([
            Keyword(keyword="ai patent filing strategy for startups", cluster="AI patents", intent="High", volume=1400, difficulty=24, cpc=8.2, trend="Rising", competition_tier="low", status="selected"),
            Keyword(keyword="provisional patent checklist", cluster="Provisional patents", intent="High", volume=1200, difficulty=19, cpc=6.7, trend="Stable", competition_tier="low", status="clustered"),
            Keyword(keyword="office action response strategy", cluster="USPTO process", intent="Medium", volume=800, difficulty=33, cpc=7.4, trend="Stable", competition_tier="medium", status="discovered"),
        ])
    if db.query(Article).count() == 0:
        db.add_all([
            Article(title="AI patent filing strategy for startups", primary_keyword="ai patent filing strategy for startups", status="Reviewing", seo_score=88, readability_score=73, metadata_json={"authoringMode": "AI + optimization"}),
            Article(title="How much does patent filing cost in the United States?", primary_keyword="patent filing cost in the united states", status="Published", seo_score=91, readability_score=78, metadata_json={"authoringMode": "AI + review"}),
        ])
    if db.query(PublishingJob).count() == 0:
        db.add_all([
            PublishingJob(status="published", destination="WordPress", detail="Published with category and featured image."),
            PublishingJob(status="processing", destination="WordPress", detail="Queued for editorial review before publishing."),
            PublishingJob(status="failed", destination="WordPress", detail="Category resolution failed; retry available."),
        ])
    if db.query(ActivityLog).count() == 0:
        db.add_all([
            ActivityLog(title="AI Writer completed", message="Drafted AI patent filing strategy for startups with FAQ schema.", actor="Article generation queue", status="success"),
            ActivityLog(title="Publishing retried", message="WordPress media upload recovered after one retry.", actor="Publishing queue", status="warning"),
            ActivityLog(title="Search Console sync", message="Imported impressions and CTR snapshots for published articles.", actor="Reporting queue", status="success"),
        ])
    if db.query(AutomationRule).count() == 0:
        now = datetime.now(timezone.utc)
        db.add_all([
            AutomationRule(name="Daily keyword research", description="Discover low competition, high intent patent-law topics.", schedule="Every day at 07:00 IST", state="active", queue_name="keyword-research", job_payload={"mode": "daily"}, last_run_at=now - timedelta(hours=8), next_run_at=now + timedelta(hours=16)),
            AutomationRule(name="Auto article generation", description="Generate article briefs and drafts from approved keywords.", schedule="Every day at 07:10 IST", state="active", queue_name="article-generation", job_payload={"mode": "daily"}, last_run_at=now - timedelta(hours=7, minutes=50), next_run_at=now + timedelta(hours=16, minutes=10)),
            AutomationRule(name="Weekly SEO report", description="Send performance summary to operations.", schedule="Every Monday at 09:00 IST", state="paused", queue_name="reporting", job_payload={"mode": "weekly"}, last_run_at=now - timedelta(days=6), next_run_at=now + timedelta(days=1)),
        ])
    db.commit()
