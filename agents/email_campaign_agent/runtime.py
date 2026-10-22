"""Bounded mailbox/event monitoring and consent-gated SES dispatch.

Draft tasks never call this sender. All sending switches are disabled in the
current deployment; an ambiguous acceptance is never automatically resent.
"""
from __future__ import annotations

import json
import time
import httpx
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from shared.lexmom_email_transport import EmailTransportSettings, build_email_request, scoped_session
from shared.lexmom_gmail import Gmail, MailboxError
from .models import Consent, Settings
from .store import Store, now
from .tools import load_campaigns, mime_message, render_email


def recent(timestamp, seconds=300):
    try:
        value=datetime.fromisoformat(timestamp)
        return value.tzinfo is not None and 0<=(datetime.now(timezone.utc)-value).total_seconds()<=seconds
    except (ValueError,TypeError): return False


def collect_prospects(records, store):
    """Keep sourced contacts with explicit holds; qualification is not permission."""
    from agents.prospect_research_agent.models import FirmRecord
    count=0
    for item in records:
        firm=FirmRecord.model_validate(item)
        for contact in firm.contacts:
            if not contact.email: continue
            holds=list(contact.readiness_reasons)
            if firm.provenance!='live' or firm.fit_status!='qualified' or not contact.research_ready:
                holds.append('Qualified live research and fresh email verification required')
            products=[product for product,fit in firm.product_assessments.items() if fit.status in {'potential_fit','confirmed_need'}]
            if not products: holds.append('Product relevance is unresolved')
            # A combined route is one five-message sequence, not two sequences.
            selected='both' if firm.primary_product=='both' and set(products)=={'manage','launch'} else firm.primary_product if firm.primary_product in products else None
            if not selected:
                preferred=[product for product in products if (store.consent_for(contact.email,product) or {}).get('series_permitted')]
                selected=preferred[0] if len(preferred)==1 else None
            if not selected: holds.append('Choose one product based on recipient preference')
            consent=store.consent_for(contact.email, selected) if selected else None
            if not consent or not consent.get('series_permitted'):
                holds.append('Documented permission for the five-message series required')
            brief=next((value for value in firm.personalization_briefs if value.email.lower()==contact.email.lower() and value.product==selected),None)
            intro=('Your published page mentions: “'+brief.facts[0].excerpt[:240]+'”.') if brief and brief.facts else None
            store.save_contact(contact.email,{'firm':firm.name,'contact_name':contact.name if contact.inbox_type=='named' else None,
                'inbox_type':contact.inbox_type,'product':selected,'source_website':firm.website,
                'research_ready':contact.research_ready,'researched_at':firm.researched_at,'verified_at':contact.verified_at,
                'product_policy_version':firm.qualification_policy_version,'sourced_intro':intro,
                'personalization':brief.model_dump() if brief else None},list(dict.fromkeys(holds)))
            count+=1
    return count


def collect_saved_prospects(store):
    """Import existing inventory only; never start searches, verification or AI calls."""
    from agents.lexmom_marketing_agent.agent import get_dashboard_data
    snapshot=get_dashboard_data()
    if snapshot.get('inventoryError') or snapshot.get('profileError'):
        raise ValueError('Saved research inventory needs attention')
    records=snapshot.get('prospectInventory',[])
    count=collect_prospects(records[:500],store)
    store.set_metadata('research_handoff',{'last_checked':now(),'firms_checked':len(records[:500]),'contacts_updated':count})
    return count


def enroll(store, settings, consent, contact):
    """Prepare durable actions, but deliberately do not queue or arm a campaign."""
    consent=Consent.model_validate(consent)
    if not consent.series_permitted or not contact.get('research_ready'):
        raise ValueError('Series permission and qualified contact research are required')
    if contact.get('product')!=consent.product:
        raise ValueError('Consent and selected product must agree')
    store.save_consent(consent)
    campaign=next(c for c in load_campaigns() if c.product==consent.product)
    start=datetime.fromisoformat(consent.recorded_at)
    if start.tzinfo is None: raise ValueError('Consent timestamp must include its timezone')
    keys=[]
    for step in campaign.steps:
        due=start+timedelta(days=step.offset_days)
        rendered=render_email(campaign,step,settings,email=consent.email,
                              contact_name=contact.get('contact_name'),firm_name=contact.get('firm'),
                              sourced_intro=contact.get('sourced_intro') if step.day==1 else None)
        keys.append(store.prepare(consent.email,campaign.product,step.day,campaign.version,due.isoformat(),rendered))
    return keys


def poll_events(store, session, transport):
    from botocore.config import Config
    client=session.client('sqs', config=Config(connect_timeout=5,read_timeout=20,retries={'total_max_attempts':3,'mode':'standard'}))
    result=client.receive_message(QueueUrl=transport.events_queue_url,MaxNumberOfMessages=10,WaitTimeSeconds=0)
    accepted=0; notices=0
    for message in result.get('Messages',[]):
        try:
            document=json.loads(message['Body'])
            if isinstance(document,dict) and isinstance(document.get('Message'),str): document=json.loads(document['Message'])
            if not isinstance(document,dict) or not document.get('mail'):
                notices+=1; continue
            store.ingest_event(document)
        except (ValueError,TypeError,KeyError):
            # Leave an unrecognized notice for the configured DLQ, rather than losing data.
            notices+=1; continue
        client.delete_message(QueueUrl=transport.events_queue_url,ReceiptHandle=message['ReceiptHandle']); accepted+=1
    store.set_metadata('event_status',{'last_checked':now(),'processed':accepted,'unrecognized_retained':notices})
    return accepted


def send_reserved(key, store, settings, transport, gmail, session):
    """One recipient per action; bulk work is a bounded series of durable actions."""
    if not transport.send_enabled or not transport.campaigns_enabled:
        raise PermissionError('Campaign sending is disabled')
    if not settings.postal_address or len(settings.unsubscribe_secret.get_secret_value())<32:
        raise PermissionError('Sender identity and unsubscribe configuration require approval')
    mailbox=store.metadata('mailbox_status',{})
    if not mailbox.get('connected') or not recent(mailbox.get('last_synced')):
        raise PermissionError('Fresh mailbox monitoring is required before dispatch')
    candidate=store.action(key)
    if not candidate: return False
    consent=store.consent_for(candidate['email'],candidate['product'])
    if not consent or not consent.get('series_permitted'):
        raise PermissionError('Series recipient permission is required')
    campaign=next((c for c in load_campaigns() if c.product==candidate['product']),None)
    if not campaign or candidate['version']!=campaign.version or not 1<=candidate['day']<=5:
        raise PermissionError('Obsolete campaign draft cannot be dispatched')
    if not store.prior_send_accepted(key):
        raise PermissionError('A follow-up requires confirmed acceptance of its preceding sequence email')
    contact=store.contact(candidate['email'])
    if not contact or contact['hold_reasons'] or not contact['data'].get('research_ready'):
        raise PermissionError('Contact research or recipient eligibility is held')
    if contact['data'].get('product') != candidate['product']:
        raise PermissionError('Selected product and researched contact must agree')
    if not recent(contact['data'].get('verified_at'),7*86400) or not recent(contact['data'].get('researched_at'),7*86400):
        raise PermissionError('Contact research or verification requires refreshing')
    local=datetime.now(timezone.utc).astimezone(ZoneInfo(consent['timezone']))
    if local.weekday()>=5 or not 9<=local.hour<17: return False
    last=store.metadata('last_dispatch_at')
    if last and recent(last,60): return False
    configuration=session.client('sesv2').get_configuration_set(ConfigurationSetName=transport.configuration_set)
    if configuration.get('SendingOptions',{}).get('SendingEnabled') is not True:
        raise PermissionError('Dedicated SES sending configuration is disabled')
    row=store.reserve(key,settings.daily_cap)
    if not row: return False
    rendered=json.loads(row['document'])
    request=build_email_request(transport,to=row['email'],subject=rendered['subject'],text=rendered['text'])
    request['Content']['Simple']['Body']['Html']={'Data':rendered['html'],'Charset':'UTF-8'}
    request['Content']['Simple']['Headers']=[{'Name':'List-Unsubscribe','Value':'<'+rendered['unsubscribe_url']+'>'},
                                          {'Name':'List-Unsubscribe-Post','Value':'List-Unsubscribe=One-Click'}]
    request['EmailTags']=[{'Name':'lexmom-action','Value':key},{'Name':'lexmom-product','Value':row['product']}]
    # SDK retries are disabled for SendEmail: an accepted request with a lost response must not replay.
    from botocore.config import Config
    sender=session.client('sesv2',config=Config(connect_timeout=5,read_timeout=20,retries={'total_max_attempts':1}))
    try:
        accepted=sender.send_email(**request)
        provider_id=accepted['MessageId']
    except Exception:
        store.outcome(key,'unknown',error='Provider acceptance is unknown; reconcile events before any retry')
        return False
    store.outcome(key,'sent',provider_id=provider_id)
    mime=mime_message(rendered,sender=transport.from_address,recipient=row['email'],reply_to=transport.reply_to,action_key=key)
    try: identifier=gmail.archive_sent(mime,key,store)
    except MailboxError:
        store.outcome(key,'archive_pending',error='Email accepted; sent-copy archive requires reconciliation')
        return True
    store.outcome(key,'sent',gmail_id=identifier)
    return True


def reconcile_archives(store, gmail, transport):
    archived = 0
    for row in store.archives_pending():
        rendered = json.loads(row['document'])
        raw = mime_message(rendered, sender=transport.from_address, recipient=row['email'],
                           reply_to=transport.reply_to, action_key=row['action_key'])
        try:
            identifier = gmail.archive_sent(raw, row['action_key'], store)
        except MailboxError:
            store.outcome(row['action_key'], 'archive_pending', error='Sent-copy insertion needs reconciliation; email will not be resent')
            continue
        store.outcome(row['action_key'], 'sent', gmail_id=identifier)
        archived += 1
    return archived


def monitor_once(settings=None, store=None, gmail=None, session=None, transport=None):
    settings=settings or Settings.from_env(); store=store or Store(settings.state_dir)
    result={'checked_at':now(),'campaigns_enabled':False,'emails_sent':0,'mailbox_connected':False,'events_processed':0}
    try:
        result['contacts_updated']=collect_saved_prospects(store)
    except (ValueError,OSError,TypeError):
        result['research_error']='Saved prospect handoff needs attention'
    owned=gmail is None
    try:
        gmail=gmail or Gmail(settings)
        result['mailbox']=gmail.sync(store); result['mailbox_connected']=True
        transport=transport or EmailTransportSettings.from_env()
        result['archives_reconciled']=reconcile_archives(store,gmail,transport)
    except (MailboxError,httpx.HTTPError) as exc:
        store.set_metadata('mailbox_status',{'connected':False,'last_checked':now(),'reason':str(exc)[:300]})
        result['mailbox_error']='Mailbox connection needs attention'
    finally:
        if gmail and owned: gmail.close()
    try:
        transport=transport or EmailTransportSettings.from_env()
        session=session or scoped_session(transport)
        result['events_processed']=poll_events(store,session,transport)
    except Exception:
        result['event_error']='Delivery-event connection needs attention'
    store.set_metadata('monitor_status',result)
    return result


if __name__=='__main__':
    from shared.config import PROJECT_ROOT
    print(json.dumps(monitor_once(),indent=2))
