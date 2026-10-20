"""SES setup and safe request construction; no send operation or campaign worker."""
from __future__ import annotations

import json
import os
import re
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

PREFIX = 'LEXMOM_EMAIL_AGENT_'
ADDRESS = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}\Z")


def address(value: str) -> str:
    if not isinstance(value, str) or len(value) > 254 or not ADDRESS.fullmatch(value):
        raise ValueError('Invalid email address or header characters')
    local, domain = value.rsplit('@', 1)
    if '..' in value or local.startswith('.') or local.endswith('.'):
        raise ValueError('Invalid email address')
    return local + '@' + domain.casefold()


class EmailTransportSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    region: str
    identity_domain: str
    mail_from_domain: str
    from_address: str
    reply_to: str
    demo_to: str
    configuration_set: str
    role_arn: str = Field(repr=False)
    events_queue_url: str = Field(repr=False)
    send_enabled: bool = False
    campaigns_enabled: bool = False

    @model_validator(mode='after')
    def validate_identity(self):
        for name in ('from_address', 'reply_to', 'demo_to'):
            address(getattr(self, name))
        if self.from_address.rsplit('@', 1)[-1] != self.identity_domain:
            raise ValueError('Sender must belong to configured identity')
        if not self.mail_from_domain.endswith('.' + self.identity_domain):
            raise ValueError('MAIL FROM must be a separate subdomain of the identity')
        if not re.fullmatch(r'[a-z]{2}-[a-z]+-\d', self.region):
            raise ValueError('Invalid AWS region')
        if not re.fullmatch(r'arn:aws:iam::\d{12}:role/[A-Za-z0-9+=,.@_/-]+', self.role_arn):
            raise ValueError('Invalid scoped role identifier')
        account = self.role_arn.split(':')[4]
        if not re.fullmatch(r'https://sqs\.' + re.escape(self.region) + r'\.amazonaws\.com/' + account + r'/[A-Za-z0-9_-]+', self.events_queue_url):
            raise ValueError('Event queue must match the scoped account and region')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', self.configuration_set):
            raise ValueError('Invalid SES configuration name')
        return self

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None):
        values = os.environ if values is None else values
        names = {'region':'AWS_REGION','identity_domain':'IDENTITY_DOMAIN','mail_from_domain':'MAIL_FROM_DOMAIN',
            'from_address':'FROM','reply_to':'REPLY_TO','demo_to':'DEMO_TO','configuration_set':'CONFIGURATION_SET',
            'role_arn':'ROLE_ARN','events_queue_url':'EVENTS_QUEUE_URL'}
        missing = [PREFIX + name for name in names.values() if not values.get(PREFIX + name)]
        if missing:
            raise ValueError('Missing email configuration: ' + ', '.join(missing))
        data = {field: values[PREFIX + name] for field, name in names.items()}
        for field, name in [('send_enabled', 'SEND_ENABLED'), ('campaigns_enabled', 'CAMPAIGNS_ENABLED')]:
            value = values.get(PREFIX + name, 'false').casefold()
            if value not in {'true', 'false'}:
                raise ValueError(PREFIX + name + ' must be true or false')
            data[field] = value == 'true'
        return cls.model_validate(data)


def scoped_session(settings):
    """Use the EC2 instance role, never unrelated env/static developer credentials."""
    import boto3
    import botocore.session
    from botocore.config import Config
    provider = botocore.session.get_session().get_component('credential_provider').get_provider('iam-role')
    credentials = provider.load()
    if credentials is None:
        raise RuntimeError('EC2 role credentials unavailable; no static-key fallback')
    frozen = credentials.get_frozen_credentials()
    base = boto3.Session(aws_access_key_id=frozen.access_key, aws_secret_access_key=frozen.secret_key,
        aws_session_token=frozen.token, region_name=settings.region)
    result = base.client('sts', config=Config(connect_timeout=5, read_timeout=10, retries={'total_max_attempts':2})).assume_role(
        RoleArn=settings.role_arn, RoleSessionName='lexmom-email-readiness', DurationSeconds=900)['Credentials']
    return boto3.Session(aws_access_key_id=result['AccessKeyId'],aws_secret_access_key=result['SecretAccessKey'],
        aws_session_token=result['SessionToken'],region_name=settings.region)


def check_readiness(settings, session=None):
    """Read account/identity/queue state without consuming messages or sending mail."""
    from botocore.config import Config
    session = session or scoped_session(settings)
    options = Config(connect_timeout=5, read_timeout=10, retries={'total_max_attempts':2})
    ses = session.client('sesv2', config=options)
    account = ses.get_account()
    identity = ses.get_email_identity(EmailIdentity=settings.identity_domain)
    configuration = ses.get_configuration_set(ConfigurationSetName=settings.configuration_set)
    destinations = ses.get_configuration_set_event_destinations(ConfigurationSetName=settings.configuration_set)
    queue = session.client('sqs', config=options).get_queue_attributes(QueueUrl=settings.events_queue_url,
        AttributeNames=['SqsManagedSseEnabled','RedrivePolicy','MessageRetentionPeriod'])['Attributes']
    try:
        recovery=json.loads(queue.get('RedrivePolicy','{}'))
        expected_prefix='arn:aws:sqs:'+settings.region+':'+settings.role_arn.split(':')[4]+':'
        queue_recovery=bool(recovery.get('deadLetterTargetArn','').startswith(expected_prefix)) and int(recovery.get('maxReceiveCount',0))>0
    except (ValueError,TypeError,AttributeError):
        queue_recovery=False
    checks = {'production_access':account.get('ProductionAccessEnabled') is True,
        'account_sending_enabled':account.get('SendingEnabled') is True,
        'account_healthy':account.get('EnforcementStatus') == 'HEALTHY',
        'identity_verified':identity.get('VerifiedForSendingStatus') is True and identity.get('VerificationStatus') == 'SUCCESS',
        'dkim_verified':identity.get('DkimAttributes',{}).get('Status') == 'SUCCESS' and identity.get('DkimAttributes',{}).get('SigningEnabled') is True,
        'mail_from_verified':identity.get('MailFromAttributes',{}).get('MailFromDomain') == settings.mail_from_domain and identity.get('MailFromAttributes',{}).get('MailFromDomainStatus') == 'SUCCESS',
        'mail_from_rejects_failure':identity.get('MailFromAttributes',{}).get('BehaviorOnMxFailure') == 'REJECT_MESSAGE',
        'default_configuration_attached':identity.get('ConfigurationSetName') == settings.configuration_set,
        'tls_required':configuration.get('DeliveryOptions',{}).get('TlsPolicy') == 'REQUIRE',
        'bounce_complaint_suppression':set(configuration.get('SuppressionOptions',{}).get('SuppressedReasons',[])) == {'BOUNCE','COMPLAINT'},
        'events_configured':any(item.get('Enabled') and {'SEND','DELIVERY','BOUNCE','COMPLAINT'}.issubset(item.get('MatchingEventTypes',[])) and item.get('SnsDestination',{}).get('TopicArn') for item in destinations.get('EventDestinations',[])),
        'queue_encrypted':queue.get('SqsManagedSseEnabled') == 'true',
        'queue_recovery_configured':queue_recovery and int(queue.get('MessageRetentionPeriod','0')) >= 1209600}
    sending = configuration.get('SendingOptions',{}).get('SendingEnabled') is True
    return {'setup_verified':all(checks.values()),'checks':checks,
        'ses_sending_enabled_for_configuration':sending,'runtime_send_enabled':settings.send_enabled,
        'campaigns_enabled':settings.campaigns_enabled,'delivery_test_verified':False,
        'mailbox_sync_configured':False,'from_address':settings.from_address,'reply_to':settings.reply_to,'demo_to':settings.demo_to}


def build_email_request(settings, *, to, subject, text):
    """Pure request builder for a later approved sender; this function never sends."""
    recipient = address(to)
    if not isinstance(subject,str) or not subject or len(subject) > 200 or any(ch in subject for ch in '\r\n\x00'):
        raise ValueError('Subject is missing, too long or contains header characters')
    if not isinstance(text,str) or not text or len(text.encode('utf-8')) > 200000:
        raise ValueError('Email text is missing or too large')
    return {'FromEmailAddress':settings.from_address,'ReplyToAddresses':[settings.reply_to],
        'Destination':{'ToAddresses':[recipient]},'ConfigurationSetName':settings.configuration_set,
        'Content':{'Simple':{'Subject':{'Data':subject,'Charset':'UTF-8'},'Body':{'Text':{'Data':text,'Charset':'UTF-8'}}}}}


def build_demo_notification(settings, *, subject, text):
    return build_email_request(settings,to=settings.demo_to,subject=subject,text=text)


if __name__ == '__main__':
    from shared.config import PROJECT_ROOT
    print(json.dumps(check_readiness(EmailTransportSettings.from_env()),indent=2))
