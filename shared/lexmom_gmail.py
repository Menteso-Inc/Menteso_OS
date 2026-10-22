"""Dedicated Gmail read/archive transport: no send, label mutation or deletion API."""
from __future__ import annotations

import base64
import html
import json
import time
from email.utils import parseaddr
from html.parser import HTMLParser

import httpx


class MailboxError(RuntimeError):
    pass


class HistoryExpired(MailboxError):
    pass


class MessageGone(MailboxError):
    pass


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.hidden=0
    def handle_starttag(self, tag, attrs):
        if tag in {'style','script'}: self.hidden += 1
        if tag in {'p','br','div','li'}: self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in {'style','script'}: self.hidden=max(0,self.hidden-1)
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


def normalize_message(message, mailbox):
    payload=message.get('payload') or {}
    headers={item['name'].lower():item.get('value','') for item in payload.get('headers',[])}
    plain=[]; rich=[]
    def collect(part):
        encoded=(part.get('body') or {}).get('data')
        if encoded and part.get('mimeType') in {'text/plain','text/html'}:
            try: text=base64.urlsafe_b64decode(encoded+'='*((-len(encoded))%4)).decode('utf-8',errors='replace')
            except (ValueError,TypeError): text=''
            (plain if part.get('mimeType')=='text/plain' else rich).append(text[:20000])
        for child in part.get('parts') or []: collect(child)
    collect(payload)
    if not plain and rich:
        parser=TextOnly(); parser.feed('\n'.join(rich)); plain=[''.join(parser.parts)]
    labels=message.get('labelIds') or []
    sender=parseaddr(headers.get('from',''))[1].lower()
    return {'message_id':message['id'],'thread_id':message.get('threadId',''),
            'subject':headers.get('subject','(No subject)')[:250],'from':headers.get('from','')[:300],
            'to':headers.get('to','')[:500],'sender_email':sender,
            'direction':'sent' if 'SENT' in labels else 'incoming',
            'labels':labels,'body':'\n'.join(plain)[:20000] or html.unescape(message.get('snippet','')),
            'rfc_message_id':headers.get('message-id','')[:500],
            'is_automated':headers.get('auto-submitted','no').casefold()!='no' or
                headers.get('precedence','').casefold() in {'bulk','list','junk'},
            'in_reply_to':headers.get('in-reply-to','')[:1000],
            'received_at_ms':message.get('internalDate'),
            'mailbox':mailbox,'source':'gmail_api'}


class Gmail:
    def __init__(self, settings, *, client=None):
        self.settings=settings
        if not settings.gmail_enabled or not settings.gmail_credentials_present:
            raise MailboxError('Dedicated Gmail authorization is not configured')
        if not settings.oauth_production:
            raise MailboxError('Gmail app production status has not been verified')
        self.client=client or httpx.Client(timeout=httpx.Timeout(20,connect=10),trust_env=False)
        self.token=None; self.expires_at=0; self.verified=False

    def close(self):
        self.client.close()

    def refresh(self):
        from agents.email_campaign_agent.models import SCOPES
        if self.token and time.monotonic()<self.expires_at: return
        for attempt in range(3):
            try:
                response=self.client.post('https://oauth2.googleapis.com/token',data={
                    'client_id':self.settings.google_client_id.get_secret_value(),
                    'client_secret':self.settings.google_client_secret.get_secret_value(),
                    'refresh_token':self.settings.google_refresh_token.get_secret_value(),'grant_type':'refresh_token'})
            except httpx.TransportError:
                if attempt==2:
                    raise MailboxError('Gmail token service could not be reached after bounded retries') from None
                time.sleep(.5*(attempt+1));continue
            if response.status_code in {429,500,502,503,504} and attempt<2:
                time.sleep(.5*(attempt+1));continue
            break
        if response.status_code!=200:
            raise MailboxError('Gmail authorization expired or was rejected; reconnect the dedicated mailbox')
        data=response.json()
        if not SCOPES.issubset(set(data.get('scope','').split())):
            raise MailboxError('Gmail read/archive permissions are missing or unverified')
        self.token=data['access_token']; self.expires_at=time.monotonic()+max(0,int(data.get('expires_in',3600))-60)

    def request(self, method, path, *, parameters=None, payload=None):
        if method!='GET' and (method,path)!=('POST','messages'):
            raise MailboxError('Only read and sent-copy insertion are permitted')
        self.refresh()
        for attempt in range(3):
            try:
                response=self.client.request(method,'https://gmail.googleapis.com/gmail/v1/users/me/'+path,
                    params=parameters,json=payload,headers={'Authorization':'Bearer '+self.token})
            except httpx.TransportError:
                if method!='GET' or attempt==2:
                    raise MailboxError('Gmail request outcome is unavailable; reconcile before retrying writes') from None
                time.sleep(.25*(attempt+1)); continue
            if response.status_code==404 and path=='history': raise HistoryExpired('Gmail history cursor expired')
            if response.status_code==404 and path.startswith('messages/'):
                raise MessageGone('Message was removed during synchronization')
            if response.status_code in {429,500,502,503,504} and method=='GET' and attempt<2:
                time.sleep(.25*(attempt+1)); continue
            if response.status_code!=200:
                raise MailboxError('Gmail request was rejected; inspect connection readiness')
            return response.json()
        raise MailboxError('Gmail read retries exhausted')

    def profile(self):
        profile=self.request('GET','profile')
        if profile.get('emailAddress','').lower()!=self.settings.mailbox.lower():
            raise MailboxError('Authorized Gmail mailbox does not match configured Lexmom identity')
        self.verified=True
        return profile

    def sync(self, store):
        profile=self.profile()
        cursor=store.metadata('gmail_history')
        ids=set(); deleted=set(); final_cursor=profile.get('historyId'); full=not cursor
        if cursor:
            page=None
            try:
                for _ in range(20):
                    query={'startHistoryId':cursor,'maxResults':100}
                    if page: query['pageToken']=page
                    data=self.request('GET','history',parameters=query)
                    for history in data.get('history',[]):
                        for item in history.get('messages',[]): ids.add(item['id'])
                        for kind in ('messagesAdded','labelsAdded','labelsRemoved'):
                            for item in history.get(kind,[]): ids.add(item['message']['id'])
                        for item in history.get('messagesDeleted',[]): deleted.add(item['message']['id'])
                    final_cursor=data.get('historyId',final_cursor); page=data.get('nextPageToken')
                    if not page: break
                else: raise MailboxError('Mailbox history exceeds one bounded synchronization batch')
            except HistoryExpired:
                full=True; ids.clear(); deleted.clear()
        if full:
            page=None
            while len(ids)<self.settings.initial_mail_limit:
                query={'maxResults':min(100,self.settings.initial_mail_limit-len(ids)),'includeSpamTrash':'true'}
                if page: query['pageToken']=page
                data=self.request('GET','messages',parameters=query)
                ids.update(item['id'] for item in data.get('messages',[])); page=data.get('nextPageToken')
                if not page: break
        fetched=0
        for identifier in sorted(ids-deleted):
            try: message=self.request('GET','messages/'+identifier,parameters={'format':'full'})
            except MessageGone:
                store.remove_mail(identifier)
                continue
            store.save_mail(normalize_message(message,self.settings.mailbox)); fetched+=1
        for identifier in deleted: store.remove_mail(identifier)
        # Commit cursor only after all fetched messages are durable; a failure can be replayed safely.
        store.set_metadata('gmail_history',final_cursor)
        from agents.email_campaign_agent.store import now
        status={'connected':True,'mailbox':self.settings.mailbox,'last_synced':now(),'messages_updated':fetched,'full_sync':full,'sent_archival_supported':True}
        store.set_metadata('mailbox_status',status)
        return status

    def archive_sent(self, mime_bytes, action_key, store):
        self.profile()
        # A lost insertion response is reconciled by the stable archive header before another insert.
        marker='lexmom-'+action_key+'@meetlexmom.com'
        existing=self.request('GET','messages',parameters={'q':'rfc822msgid:'+marker,'maxResults':2,'includeSpamTrash':'true'})
        if existing.get('messages'): return existing['messages'][0]['id']
        # An interrupted insert may still become visible later. Search again on future
        # runs, but do not repeat an insert whose acceptance is unknown.
        attempt_name='gmail_insert_attempt_'+action_key
        if store.metadata(attempt_name):
            raise MailboxError('Sent-copy insertion is unresolved; manual review required before another insertion')
        raw=base64.urlsafe_b64encode(mime_bytes).decode().rstrip('=')
        from agents.email_campaign_agent.store import now
        store.set_metadata(attempt_name,{'attempted_at':now()})
        inserted=self.request('POST','messages',payload={'raw':raw,'labelIds':['SENT']},parameters={'internalDateSource':'dateHeader'})
        return inserted['id']
