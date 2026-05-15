from datetime import datetime
from pydantic import BaseModel, Field


class KpiCard(BaseModel):
    label: str
    value: int | float | str
    delta: str | None = None
    tone: str = "default"
    help_text: str | None = Field(default=None, alias="helpText")


class ActivityLogOut(BaseModel):
    id: str
    title: str
    message: str
    actor: str
    status: str
    created_at: datetime


class PublishingLogOut(BaseModel):
    id: str
    article_title: str = Field(alias="articleTitle")
    destination: str
    status: str
    created_at: datetime = Field(alias="createdAt")
    detail: str


class AutomationRuleOut(BaseModel):
    id: str
    name: str
    schedule: str
    state: str
    last_run_at: datetime | None = Field(default=None, alias="lastRunAt")
    next_run_at: datetime | None = Field(default=None, alias="nextRunAt")
    description: str


class DashboardSummaryOut(BaseModel):
    kpis: list[KpiCard]
    activity_feed: list[ActivityLogOut] = Field(alias="activityFeed")
    publishing_logs: list[PublishingLogOut] = Field(alias="publishingLogs")
    automation_rules: list[AutomationRuleOut] = Field(alias="automationRules")
    seo_score: int = Field(alias="seoScore")
    indexed_pages: int = Field(alias="indexedPages")
    organic_traffic: int = Field(alias="organicTraffic")


class KeywordOut(BaseModel):
    id: str
    keyword: str
    cluster: str
    intent: str
    volume: int
    difficulty: float
    cpc: float
    trend: str
    competition_tier: str = Field(alias="competitionTier")
    status: str


class ArticleOut(BaseModel):
    id: str
    title: str
    primary_keyword: str = Field(alias="primaryKeyword")
    status: str
    seo_score: float = Field(alias="seoScore")
    readability_score: float = Field(alias="readabilityScore")
    updated_at: datetime = Field(alias="updatedAt")
    authoring_mode: str = Field(alias="authoringMode")


class JobRequestIn(BaseModel):
    job_type: str = Field(alias="jobType")
    input_ref: str = Field(alias="inputRef")
    payload: dict = Field(default_factory=dict)


class JobResponseOut(BaseModel):
    job_id: str = Field(alias="jobId")
    job_type: str = Field(alias="jobType")
    status: str
    message: str


class SettingUpsertIn(BaseModel):
    key: str
    value: dict
    is_secret: bool = Field(default=False, alias="isSecret")

