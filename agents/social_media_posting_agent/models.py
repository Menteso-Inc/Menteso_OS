"""Validated content and dedicated credentials. Discovery never publishes."""
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from shared.config import PROJECT_ROOT

PREFIX = 'LEXMOM_SOCIAL_AGENT_'
YOUTUBE_SCOPES = frozenset({'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly', 'https://www.googleapis.com/auth/yt-analytics.readonly'})


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Draft(Contract):
    key: str = Field(pattern=r'^[a-z0-9-]{1,80}$')
    product: Literal['manage', 'launch']
    platform: Literal['linkedin', 'youtube']
    title: str = Field(min_length=1, max_length=100)
    caption: str = Field(min_length=20, max_length=3000)
    image: str = Field(pattern=r'^lexmom-(manage|launch)-day0[1-7]-v3\.png$')
    video: str | None = Field(default=None, pattern=r'^[a-z0-9-]{1,80}\.mp4$')
    proposed_day: int = Field(ge=1, le=7)
    revision: int = Field(default=1, ge=1)
    status: Literal['draft','approved','scheduled','publishing','processing','uploaded','published','needs_reconciliation','failed','paused'] = 'draft'
    privacy_status: Literal['private','unlisted','public'] = 'private'
    created_at: datetime | None = None
    published_at: datetime | None = None
    scheduled_at: datetime | None = None
    approval_digest: str | None = None
    asset_digest: str | None = None
    destination_digest: str | None = None
    receipt_key: str | None = None
    note: str = Field(default='', max_length=500)

    @model_validator(mode='after')
    def valid_content(self):
        if self.product not in self.image:
            raise ValueError('Image must match the product')
        if any(c in self.title for c in '\r\n\x00') or '\x00' in self.caption:
            raise ValueError('Invalid content characters')
        if self.scheduled_at and self.scheduled_at.utcoffset() is None:
            raise ValueError('Scheduled time requires a timezone')
        if any(value and value.utcoffset() is None for value in (self.created_at,self.published_at)):
            raise ValueError('Post timestamps require a timezone')
        for url in re.findall(r'https?://\S+',self.caption):
            parsed=urlsplit(url)
            if parsed.scheme!='https' or parsed.hostname!='lexmom.com' or parsed.username or parsed.password or parsed.path.rstrip('/') not in {'/'+self.product}:
                raise ValueError('Social campaign links must point to the matching LexMom product')
        return self

    def digest(self):
        fields = self.model_dump(mode='json', include={'key','product','platform','title','caption','image','video','privacy_status','revision','scheduled_at','asset_digest','destination_digest'})
        return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


class Settings(Contract):
    model_config = ConfigDict(extra='forbid', frozen=True)
    state_dir: Path
    env_file: Path
    publishing_enabled: bool = False
    paid_generation_enabled: bool = False
    daily_cap: int = Field(default=2, ge=1, le=10)
    google_client_id: SecretStr = Field(default_factory=lambda: SecretStr(''), repr=False)
    google_client_secret: SecretStr = Field(default_factory=lambda: SecretStr(''), repr=False)
    google_refresh_token: SecretStr = Field(default_factory=lambda: SecretStr(''), repr=False)
    youtube_channel_id: SecretStr = Field(default_factory=lambda: SecretStr(''), repr=False)
    linkedin_client_id: SecretStr = Field(default_factory=lambda: SecretStr(''), repr=False)
    linkedin_client_secret: SecretStr = Field(default_factory=lambda: SecretStr(''), repr=False)
    linkedin_access_token: SecretStr = Field(default_factory=lambda: SecretStr(''), repr=False)
    linkedin_refresh_token: SecretStr = Field(default_factory=lambda: SecretStr(''), repr=False)
    linkedin_organization_urn: SecretStr = Field(default_factory=lambda: SecretStr(''), repr=False)
    linkedin_version: str = Field(default='202609', pattern=r'^20\d{4}$')
    linkedin_expires_at: int = Field(default=0,ge=0)
    linkedin_refresh_expires_at: int = Field(default=0,ge=0)
    linkedin_refresh_retry_at: int = Field(default=0,ge=0)
    linkedin_refresh_blocked: bool = False
    linkedin_product_approved: bool = False

    @classmethod
    def from_env(cls):
        primary = dotenv_values(PROJECT_ROOT/'.env') if (PROJECT_ROOT/'.env').is_file() else {}
        env_file = Path(os.getenv(PREFIX+'ENV_FILE') or primary.get(PREFIX+'ENV_FILE') or str(PROJECT_ROOT/'.env')).resolve()
        values = {**os.environ, **(dotenv_values(env_file) if env_file.is_file() else {})}
        fields = {name: values.get(PREFIX+name.upper(), '') or '' for name in (
            'google_client_id','google_client_secret','google_refresh_token','youtube_channel_id',
            'linkedin_client_id','linkedin_client_secret','linkedin_access_token','linkedin_refresh_token','linkedin_organization_urn')}
        return cls(**fields, env_file=env_file,
            state_dir=Path(values.get(PREFIX+'STATE_DIR') or PROJECT_ROOT/'runtime-data/social_media_posting_agent'),
            publishing_enabled=str(values.get(PREFIX+'PUBLISHING_ENABLED','false')).lower()=='true',
            paid_generation_enabled=str(values.get(PREFIX+'PAID_GENERATION_ENABLED','false')).lower()=='true',
            daily_cap=int(values.get(PREFIX+'DAILY_CAP') or 2), linkedin_version=values.get(PREFIX+'LINKEDIN_VERSION') or '202609',
            linkedin_expires_at=int(values.get(PREFIX+'LINKEDIN_EXPIRES_AT') or 0),
            linkedin_refresh_expires_at=int(values.get(PREFIX+'LINKEDIN_REFRESH_EXPIRES_AT') or 0),
            linkedin_refresh_retry_at=int(values.get(PREFIX+'LINKEDIN_REFRESH_RETRY_AT') or 0),
            linkedin_refresh_blocked=str(values.get(PREFIX+'LINKEDIN_REFRESH_BLOCKED','false')).lower()=='true',
            linkedin_product_approved=str(values.get(PREFIX+'LINKEDIN_PRODUCT_APPROVED','false')).lower()=='true')

    def configured(self, platform):
        if platform not in {'linkedin','youtube'}:raise ValueError('Unknown social platform')
        names = ('google_client_id','google_client_secret','google_refresh_token','youtube_channel_id') if platform=='youtube' else (
            'linkedin_client_id','linkedin_client_secret','linkedin_access_token','linkedin_organization_urn')
        return all(getattr(self, name).get_secret_value() for name in names)

    def app_configured(self, platform):
        names = ('google_client_id','google_client_secret','youtube_channel_id') if platform=='youtube' else (
            'linkedin_client_id','linkedin_client_secret','linkedin_organization_urn')
        if platform not in {'linkedin','youtube'}:raise ValueError('Unknown social platform')
        return all(getattr(self,name).get_secret_value() for name in names)

    def destination_digest(self, platform):
        if not self.app_configured(platform):raise ValueError('Configure the dedicated application and destination first')
        names=('google_client_id','youtube_channel_id') if platform=='youtube' else ('linkedin_client_id','linkedin_organization_urn')
        return hashlib.sha256(json.dumps([getattr(self,name).get_secret_value() for name in names]).encode()).hexdigest()
