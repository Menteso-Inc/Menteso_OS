"""Validated campaign contracts; mailbox credentials never appear in results."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from shared.lexmom_email_transport import address

PREFIX = 'LEXMOM_EMAIL_AGENT_'
SCOPES = frozenset({'https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.insert'})


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Step(Contract):
    day: int = Field(ge=1, le=5, description='Sequence position, not calendar day')
    kind: Literal['introduction','follow_up_1','follow_up_2','follow_up_3','feedback']
    offset_days: int = Field(ge=0,le=45)
    references_step: int | None = Field(default=None,ge=1,le=4)
    new_information: str | None = Field(default=None,min_length=10,max_length=350)
    subject: str = Field(min_length=1, max_length=150)
    subject_named: str | None = Field(default=None, min_length=1, max_length=150)
    subject_firm: str | None = Field(default=None, min_length=1, max_length=150)
    topic: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=20, max_length=5000)
    body_firm: str | None = Field(default=None, min_length=20, max_length=5000)
    image: str | None = Field(default=None,pattern=r'^lexmom-(manage|launch)-day0[1-7]-v3\.png$')
    secondary_image: str | None = Field(default=None,pattern=r'^lexmom-manage-day0[1-7]-v3\.png$')

    @field_validator('subject', 'subject_named', 'subject_firm', 'topic')
    @classmethod
    def clean_header(cls, value):
        if value is None:return value
        if any(char in value for char in '\r\n\x00'):
            raise ValueError('Header characters are not allowed')
        return value

    @field_validator('subject_named', 'subject_firm')
    @classmethod
    def simple_subject_template(cls, value, info):
        from string import Formatter
        if value is None:return value
        for _,name,spec,conversion in Formatter().parse(value):
            if name is not None and (name not in {'contact_name','firm_name'} or spec or conversion):
                raise ValueError('Subject templates support only plain contact_name and firm_name fields')
            if info.field_name=='subject_firm' and name=='contact_name':
                raise ValueError('Firm inbox subjects cannot require a named person')
        return value

    @field_validator('body','body_firm')
    @classmethod
    def grounded_body_template(cls,value):
        from string import Formatter
        if value is None:return value
        for _,name,spec,conversion in Formatter().parse(value):
            if name is not None and (name!='firm_name' or spec or conversion):
                raise ValueError('Body templates support only a plain firm_name field')
        return value


class Campaign(Contract):
    product: Literal['manage', 'launch', 'both']
    name: str = Field(min_length=1, max_length=150)
    version: str = Field(min_length=1, max_length=50)
    status: Literal['draft', 'paused'] = 'draft'
    audience: str = Field(min_length=1, max_length=1000)
    cta_url: str
    cta_label: str = Field(min_length=1, max_length=80)
    secondary_cta_url: str | None = None
    secondary_cta_label: str | None = Field(default=None,min_length=1,max_length=80)
    image: str | None = Field(default=None,pattern=r'^lexmom-(manage|launch)-day01-v3\.png$')
    steps: list[Step] = Field(min_length=5, max_length=5)

    @model_validator(mode='after')
    def consistent(self):
        if [step.day for step in self.steps] != list(range(1, 6)):
            raise ValueError('Exactly five ordered sequence drafts are required')
        if [step.kind for step in self.steps] != ['introduction','follow_up_1','follow_up_2','follow_up_3','feedback']:
            raise ValueError('Introduction, three follow-ups and final feedback are required')
        if self.steps[0].offset_days!=0 or any(b.offset_days<=a.offset_days for a,b in zip(self.steps,self.steps[1:])):
            raise ValueError('Sequence spacing must increase from the introduction')
        if self.steps[0].references_step is not None or any(s.references_step!=s.day-1 for s in self.steps[1:]):
            raise ValueError('Each follow-up must reference its immediately preceding email')
        if any(not s.new_information for s in self.steps):
            raise ValueError('Each step must explain its additional value or purpose')
        allowed = {'manage': 'https://lexmom.com/manage/book-demo', 'launch': 'https://lexmom.com/launch/'}
        primary='launch' if self.product=='both' else self.product
        if self.cta_url != allowed[primary]:
            raise ValueError('Product destination must be the approved Lexmom page')
        if self.image or any(step.image or step.secondary_image for step in self.steps):
            raise ValueError('Current campaign drafts must be image-free')
        if self.product=='both':
            if self.secondary_cta_url!=allowed['manage'] or not self.secondary_cta_label:
                raise ValueError('Combined introduction requires both approved product links')
        elif self.secondary_cta_url or self.secondary_cta_label or any(s.secondary_image for s in self.steps):
            raise ValueError('Single-product drafts cannot include another product CTA')
        return self


class Settings(Contract):
    model_config = ConfigDict(extra='forbid', frozen=True)
    mailbox: str = 'mail@lexmom.com'
    google_client_id: SecretStr = Field(default_factory=lambda: SecretStr(''), repr=False)
    google_client_secret: SecretStr = Field(default_factory=lambda: SecretStr(''), repr=False)
    google_refresh_token: SecretStr = Field(default_factory=lambda: SecretStr(''), repr=False)
    gmail_enabled: bool = False
    oauth_production: bool = False
    state_dir: Path
    public_origin: str = 'https://os.menteso.com'
    unsubscribe_secret: SecretStr = Field(default_factory=lambda: SecretStr(''), repr=False)
    postal_address: str = ''
    daily_cap: int = Field(default=10, ge=1, le=200)
    interval_seconds: int = Field(default=120, ge=60, le=3600)
    initial_mail_limit: int = Field(default=100, ge=1, le=500)

    @field_validator('mailbox')
    @classmethod
    def valid_mailbox(cls, value):
        return address(value)

    @field_validator('public_origin')
    @classmethod
    def public_url(cls, value):
        if value != 'https://os.menteso.com':
            raise ValueError('Only the approved dashboard origin is supported')
        return value

    @classmethod
    def from_env(cls, values=None):
        values = os.environ if values is None else values
        def flag(name):
            value = values.get(PREFIX + name, 'false').lower()
            if value not in {'true', 'false'}:
                raise ValueError(PREFIX + name + ' must be true or false')
            return value == 'true'
        return cls(mailbox=values.get(PREFIX+'MAILBOX', 'mail@lexmom.com'),
                   google_client_id=values.get(PREFIX+'GOOGLE_CLIENT_ID', ''),
                   google_client_secret=values.get(PREFIX+'GOOGLE_CLIENT_SECRET', ''),
                   google_refresh_token=values.get(PREFIX+'GOOGLE_REFRESH_TOKEN', ''),
                   gmail_enabled=flag('GMAIL_ENABLED'), oauth_production=flag('GOOGLE_OAUTH_PRODUCTION'),
                   state_dir=Path(values.get(PREFIX+'STATE_DIR') or Path(__file__).resolve().parents[2]/'runtime-data/email_campaign_agent'),
                   unsubscribe_secret=values.get(PREFIX+'UNSUBSCRIBE_SECRET', ''),
                   postal_address=values.get(PREFIX+'POSTAL_ADDRESS', ''),
                   daily_cap=values.get(PREFIX+'DAILY_CAP', '10'),
                   interval_seconds=values.get(PREFIX+'MONITOR_INTERVAL', '120'),
                   initial_mail_limit=values.get(PREFIX+'INITIAL_MAIL_LIMIT', '100'))

    @property
    def gmail_credentials_present(self):
        return all(secret.get_secret_value() for secret in
                   (self.google_client_id, self.google_client_secret, self.google_refresh_token))


class Consent(Contract):
    email: str
    product: Literal['manage', 'launch', 'both']
    source: str = Field(min_length=1, max_length=1000)
    recorded_at: str
    series_permitted: bool = False
    timezone: str

    _address = field_validator('email')(address)

    @field_validator('recorded_at')
    @classmethod
    def timestamp_known(cls, value):
        moment = datetime.fromisoformat(value)
        if moment.tzinfo is None:
            raise ValueError('Consent timestamp must include a timezone')
        if (moment - datetime.now(timezone.utc)).total_seconds() > 300:
            raise ValueError('Consent timestamp cannot be in the future')
        return moment.astimezone(timezone.utc).isoformat()

    @field_validator('timezone')
    @classmethod
    def timezone_known(cls, value):
        ZoneInfo(value)
        return value
