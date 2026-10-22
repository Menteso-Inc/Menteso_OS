"""Private transactional campaign state with non-replayable send reservations."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.directory.is_symlink():
            raise ValueError('Email state must not be a symlink')
        self.path = self.directory / 'email.sqlite3'
        if self.path.is_symlink():
            raise ValueError('Email database must not be a symlink')
        with self.connection() as database:
            database.executescript('''
                CREATE TABLE IF NOT EXISTS campaigns(product TEXT PRIMARY KEY,version TEXT NOT NULL,document TEXT NOT NULL,updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS contacts(email TEXT PRIMARY KEY,document TEXT NOT NULL,hold_reasons TEXT NOT NULL,updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS consent(email TEXT NOT NULL,product TEXT NOT NULL,document TEXT NOT NULL,PRIMARY KEY(email,product));
                CREATE TABLE IF NOT EXISTS suppression(email TEXT PRIMARY KEY,reason TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS actions(action_key TEXT PRIMARY KEY,email TEXT NOT NULL,product TEXT NOT NULL,day INTEGER NOT NULL,
                    version TEXT NOT NULL,due_at TEXT NOT NULL,status TEXT NOT NULL,document TEXT NOT NULL,provider_id TEXT,
                    gmail_id TEXT,error TEXT,updated TEXT NOT NULL,dispatch_at TEXT,UNIQUE(email,product,day));
                CREATE UNIQUE INDEX IF NOT EXISTS provider_unique ON actions(provider_id) WHERE provider_id IS NOT NULL;
                CREATE TABLE IF NOT EXISTS events(event_key TEXT PRIMARY KEY,action_key TEXT,event_type TEXT NOT NULL,provider_id TEXT,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS mailbox(message_id TEXT PRIMARY KEY,thread_id TEXT NOT NULL,document TEXT NOT NULL,updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS metadata(name TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reply_tasks(message_id TEXT PRIMARY KEY,kind TEXT NOT NULL,status TEXT NOT NULL,
                    document TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS interest_confirmations(email TEXT PRIMARY KEY,message_id TEXT NOT NULL,product TEXT NOT NULL,created TEXT NOT NULL);
            ''')
            # Preserve an existing pilot database when adding immutable dispatch timestamps.
            columns = {row['name'] for row in database.execute('PRAGMA table_info(actions)')}
            if 'dispatch_at' not in columns:
                database.execute('ALTER TABLE actions ADD COLUMN dispatch_at TEXT')
            event_columns = {row['name'] for row in database.execute('PRAGMA table_info(events)')}
            if 'detail' not in event_columns:
                database.execute("ALTER TABLE events ADD COLUMN detail TEXT NOT NULL DEFAULT '{}'")
        if os.name != 'nt':
            os.chmod(self.directory, 0o700)
            os.chmod(self.path, 0o600)

    @contextmanager
    def connection(self, write=False):
        database = sqlite3.connect(self.path, timeout=10)
        database.row_factory = sqlite3.Row
        database.execute('PRAGMA journal_mode=WAL')
        database.execute('PRAGMA synchronous=FULL')
        database.execute('PRAGMA busy_timeout=10000')
        try:
            if write:
                database.execute('BEGIN IMMEDIATE')
            yield database
            database.commit()
        except BaseException:
            database.rollback()
            raise
        finally:
            database.close()

    def metadata(self, name, default=None):
        with self.connection() as database:
            row = database.execute('SELECT value FROM metadata WHERE name=?', (name,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_metadata(self, name, value):
        with self.connection(write=True) as database:
            database.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', (name, json.dumps(value)))

    def install_campaigns(self, campaigns):
        with self.connection(write=True) as database:
            for campaign in campaigns:
                database.execute('INSERT OR REPLACE INTO campaigns VALUES(?,?,?,?)',
                                 (campaign.product, campaign.version, campaign.model_dump_json(), now()))
                database.execute("UPDATE actions SET status='cancelled',error='Superseded campaign definition',updated=? WHERE product=? AND status IN ('prepared','queued') AND (version<>? OR day>5)",
                                 (now(),campaign.product,campaign.version))

    def save_contact(self, email, document, holds):
        with self.connection(write=True) as database:
            database.execute('INSERT OR REPLACE INTO contacts VALUES(?,?,?,?)',
                             (email.lower(), json.dumps(document), json.dumps(holds), now()))

    def suppress(self, email, reason):
        with self.connection(write=True) as database:
            self._suppress(database, email.lower(), reason)

    @staticmethod
    def _suppress(database, email, reason):
        database.execute('INSERT OR REPLACE INTO suppression VALUES(?,?,?)', (email, reason, now()))
        database.execute("UPDATE actions SET status='cancelled',error=?,updated=? WHERE email=? AND status IN ('queued','prepared')", (reason, now(), email))

    def consent_for(self, email, product):
        with self.connection() as database:
            row = database.execute('SELECT document FROM consent WHERE email=? AND product=?', (email.lower(), product)).fetchone()
        return json.loads(row[0]) if row else None

    def save_consent(self, consent):
        with self.connection(write=True) as database:
            database.execute('INSERT OR REPLACE INTO consent VALUES(?,?,?)',
                             (consent.email.lower(), consent.product, consent.model_dump_json()))

    def prepare(self, email, product, day, version, due_at, document):
        due = datetime.fromisoformat(due_at)
        if due.tzinfo is None:
            raise ValueError('Scheduled time must include a timezone')
        due_at = due.astimezone(timezone.utc).isoformat()
        key = hashlib.sha256(f'{email.lower()}|{product}|{day}'.encode()).hexdigest()
        with self.connection(write=True) as database:
            # A new template version cannot re-queue an already attempted daily action.
            database.execute('INSERT OR IGNORE INTO actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (key,email.lower(),product,day,version,due_at,'prepared',json.dumps(document),None,None,None,now(),None))
        return key

    def reserve(self, key, daily_cap, *, current=None, min_interval_seconds=60):
        current = current or now()
        moment = datetime.fromisoformat(current)
        if moment.tzinfo is None:
            raise ValueError('Dispatch time must include a timezone')
        current = moment.astimezone(timezone.utc).isoformat()
        with self.connection(write=True) as database:
            row = database.execute('SELECT * FROM actions WHERE action_key=?', (key,)).fetchone()
            if not row or row['status'] != 'queued' or row['due_at'] > current:
                return None
            if database.execute('SELECT 1 FROM suppression WHERE email=?', (row['email'],)).fetchone():
                self._suppress(database, row['email'], 'Suppressed before dispatch')
                return None
            if not self._prior_send_accepted(database,row):
                return None
            other = database.execute("SELECT 1 FROM actions WHERE email=? AND product<>? AND status IN ('queued','dispatching','unknown')", (row['email'], row['product'])).fetchone()
            if other:
                return None
            used = database.execute("SELECT COUNT(*) FROM actions WHERE substr(dispatch_at,1,10)=?", (current[:10],)).fetchone()[0]
            if used >= daily_cap:
                return None
            previous = database.execute('SELECT value FROM metadata WHERE name=?', ('last_dispatch_at',)).fetchone()
            if previous:
                elapsed=(datetime.fromisoformat(current)-datetime.fromisoformat(json.loads(previous[0]))).total_seconds()
                if elapsed < min_interval_seconds: return None
            database.execute("UPDATE actions SET status='dispatching',updated=?,dispatch_at=? WHERE action_key=?", (current, current, key))
            database.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', ('last_dispatch_at',json.dumps(current)))
            return dict(row)

    @staticmethod
    def _prior_send_accepted(database,row):
        if row['day']==1:return True
        return database.execute("SELECT 1 FROM actions WHERE email=? AND product=? AND version=? AND day=? AND provider_id IS NOT NULL AND provider_id<>'' AND status IN ('sent','delivered','archive_pending')",
                                (row['email'],row['product'],row['version'],row['day']-1)).fetchone() is not None

    def prior_send_accepted(self,key):
        with self.connection() as database:
            row=database.execute('SELECT * FROM actions WHERE action_key=?',(key,)).fetchone()
            return row is not None and self._prior_send_accepted(database,row)

    def outcome(self, key, status, *, provider_id=None, gmail_id=None, error=None):
        allowed = {'sent','unknown','archive_pending','delivered','bounced','complained','rejected','cancelled'}
        if status not in allowed:
            raise ValueError('Invalid delivery outcome')
        with self.connection(write=True) as database:
            database.execute("UPDATE actions SET status=CASE WHEN status IN ('delivered','bounced','complained','rejected') AND ? IN ('sent','archive_pending') THEN status ELSE ? END,provider_id=COALESCE(?,provider_id),gmail_id=COALESCE(?,gmail_id),error=?,updated=? WHERE action_key=?",
                             (status,status,provider_id,gmail_id,error,now(),key))

    def contact(self, email):
        with self.connection() as database:
            row=database.execute('SELECT document,hold_reasons FROM contacts WHERE email=?',(email.lower(),)).fetchone()
        return {'data':json.loads(row[0]),'hold_reasons':json.loads(row[1])} if row else None

    def remove_mail(self, identifier):
        with self.connection(write=True) as database:
            database.execute('DELETE FROM mailbox WHERE message_id=?',(identifier,))

    def action(self, key):
        with self.connection() as database:
            row = database.execute('SELECT * FROM actions WHERE action_key=?', (key,)).fetchone()
        return dict(row) if row else None

    def ingest_event(self, document):
        event_type = document.get('eventType') or document.get('notificationType')
        if event_type not in {'Send','Delivery','Bounce','Complaint','Reject','DeliveryDelay','Rendering Failure','Open','Click'}:
            raise ValueError('Unknown provider event')
        mail = document.get('mail') or {}
        provider = mail.get('messageId')
        key = hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
        with self.connection(write=True) as database:
            if database.execute('SELECT 1 FROM events WHERE event_key=?', (key,)).fetchone():
                return False
            row = database.execute('SELECT * FROM actions WHERE provider_id=?', (provider,)).fetchone()
            tags = mail.get('tags') or {}
            tag = (tags.get('lexmom-action') or [None])[0]
            if row is None and tag:
                candidate = database.execute('SELECT * FROM actions WHERE action_key=?', (tag,)).fetchone()
                destinations = {str(value).casefold() for value in mail.get('destination', [])}
                if candidate and candidate['email'].casefold() in destinations and candidate['provider_id'] in {None, provider}:
                    row = candidate
            detail = {}
            payload = document.get(event_type.casefold()) or {}
            if event_type in {'Open','Click'}:
                detail['bot_likelihood'] = payload.get('isBotEvent') if payload.get('isBotEvent') in {'Likely','Unlikely'} else 'Unknown'
            timestamp = payload.get('timestamp')
            if isinstance(timestamp, str):
                try:
                    value = datetime.fromisoformat(timestamp.replace('Z','+00:00'))
                    if value.tzinfo is not None: detail['observed_at'] = value.astimezone(timezone.utc).isoformat()
                except ValueError: pass
            if event_type == 'Click':
                from urllib.parse import urlsplit
                try:
                    link = urlsplit(str(payload.get('link', '')))
                    products = ('launch','manage') if row and row['product']=='both' else (row['product'],) if row else ()
                    approved_origin = (link.scheme=='https' and link.hostname=='lexmom.com' and
                                       link.port in {None,443} and not link.username and not link.password)
                    clicked_product = next((product for product in products if approved_origin and
                        (link.path=='/'+product or link.path.startswith('/'+product+'/'))),None)
                    detail['product_cta'] = clicked_product is not None
                    if clicked_product: detail['clicked_product'] = clicked_product
                except ValueError: detail['product_cta'] = False
            database.execute('INSERT INTO events(event_key,action_key,event_type,provider_id,created,detail) VALUES(?,?,?,?,?,?)',
                             (key, row['action_key'] if row else None, event_type, provider, now(), json.dumps(detail)))
            if row:
                status = {'Send':'sent','Delivery':'delivered','Bounce':'bounced','Complaint':'complained','Reject':'rejected','Rendering Failure':'rejected'}.get(event_type)
                terminal = {'bounced','complained','rejected'}
                update = status and row['status'] not in terminal
                if status == 'sent' and row['status'] == 'delivered':
                    update = False
                if status == 'complained' or (status == 'bounced' and row['status'] != 'complained'):
                    update = True
                if update:
                    database.execute('UPDATE actions SET status=?,provider_id=COALESCE(provider_id,?),updated=? WHERE action_key=?', (status, provider, now(), row['action_key']))
                if event_type in {'Bounce', 'Complaint'}:
                    self._suppress(database, row['email'], event_type)
            return True

    def confirm_interest(self, email, message_id, product):
        """An operator confirms a real prospect reply; no classification is guessed."""
        if not isinstance(email,str) or not isinstance(message_id,str) or not 1<=len(message_id)<=100:
            raise ValueError('Select a lead and its actual reply')
        if product not in {'manage','launch'}: raise ValueError('Unknown product')
        with self.connection(write=True) as database:
            row=database.execute('SELECT document FROM mailbox WHERE message_id=?',(message_id,)).fetchone()
            if not row: raise ValueError('Reply not found')
            message=json.loads(row['document'])
            if (message.get('direction')!='incoming' or message.get('sender_email','').casefold()!=email.casefold()
                or message.get('is_automated') or set(message.get('labels',[])) & {'SPAM','TRASH','DRAFT'}):
                raise ValueError('An actual reply from this lead is required')
            if not database.execute('SELECT 1 FROM contacts WHERE email=?',(email.casefold(),)).fetchone():
                raise ValueError('Lead is not in the campaign contact inventory')
            database.execute('INSERT OR REPLACE INTO interest_confirmations VALUES(?,?,?,?)',
                             (email.casefold(),message_id,product,now()))

    def engagement_activity(self):
        """Return recorded lead activity only, with no mailbox bodies or IP addresses."""
        activity={}
        def item(email):
            return activity.setdefault(email.casefold(), {'opens':0,'clicks':0,'replies':0,'confirmed_interest':False,
                'last_activity_at':None,'suppressed':False})
        def seen(row, timestamp):
            if timestamp and (not row['last_activity_at'] or timestamp>row['last_activity_at']): row['last_activity_at']=timestamp
        with self.connection() as database:
            for event in database.execute('SELECT a.email,e.event_type,e.created,e.detail FROM events e JOIN actions a ON a.action_key=e.action_key'):
                detail=json.loads(event['detail']); row=item(event['email'])
                if detail.get('bot_likelihood')=='Likely': continue
                if event['event_type']=='Open': row['opens']+=1
                elif event['event_type']=='Click' and detail.get('product_cta'): row['clicks']+=1
                else: continue
                seen(row,detail.get('observed_at') or event['created'])
            for entry in database.execute('SELECT document,updated FROM mailbox'):
                message=json.loads(entry['document'])
                if message.get('direction')!='incoming' or message.get('is_automated') or set(message.get('labels',[])) & {'SPAM','TRASH','DRAFT'}: continue
                sender=message.get('sender_email','')
                if not sender: continue
                row=item(sender); row['replies']+=1
                try:
                    received=datetime.fromtimestamp(int(message['received_at_ms'])/1000,timezone.utc).isoformat()
                except (KeyError,TypeError,ValueError,OverflowError,OSError):
                    received=entry['updated']
                seen(row,received)
            for entry in database.execute('SELECT email,created FROM interest_confirmations'):
                row=item(entry['email']); row['confirmed_interest']=True; seen(row,entry['created'])
            for entry in database.execute('SELECT email,reason FROM suppression'):
                # A reply pauses automation but can still express interest. Other
                # suppression reasons take precedence over engagement temperature.
                if entry['reason']!='Reply received': item(entry['email'])['suppressed']=True
        return activity

    def archives_pending(self):
        with self.connection() as database:
            return [dict(row) for row in database.execute(
                "SELECT * FROM actions WHERE provider_id IS NOT NULL AND gmail_id IS NULL AND status IN ('sent','archive_pending','delivered') ORDER BY updated LIMIT 20")]

    def save_mail(self, document):
        with self.connection(write=True) as database:
            # Preserve first observation when Gmail replays a message after label
            # changes. Synchronizing a reply must not make its activity look new.
            database.execute('INSERT INTO mailbox VALUES(?,?,?,?) ON CONFLICT(message_id) DO UPDATE SET thread_id=excluded.thread_id,document=excluded.document',
                             (document['message_id'], document.get('thread_id',''), json.dumps(document), now()))
            if document.get('direction') == 'incoming':
                # Replies and declines stop that contact's sequences before the next send.
                sender = document.get('sender_email', '').lower()
                contact = database.execute('SELECT document FROM contacts WHERE email=?', (sender,)).fetchone()
                if contact:
                    self._suppress(database, sender, 'Reply received')
                self._reply_task(database,document,contact)

    @staticmethod
    def _reply_task(database,document,contact):
        """Triage untrusted inbound content into review tasks, with no outbound action."""
        import re
        sender=document.get('sender_email','')
        if not sender or 'SENT' in document.get('labels',[]) or any(label in document.get('labels',[]) for label in ('SPAM','TRASH','DRAFT')):
            return
        subject=document.get('subject','')
        demo=bool(re.search(r'\b(demo|walkthrough)\b',subject,re.I))
        if not contact and not demo:return
        detail=json.loads(contact['document']) if contact else {}
        product=detail.get('product')
        if product not in {'manage','launch'}:
            matches=[item for item in ('manage','launch') if re.search(r'\b'+item+r'\b',subject,re.I)]
            product=matches[0] if len(matches)==1 else None
        kind='demo_request' if demo else 'reply_review'
        task={'message_id':document['message_id'],'thread_id':document.get('thread_id',''),
              'sender':sender,'subject':subject,'product':product,'suggested_next_step':
              'Review the request and arrange a human demo.' if demo else 'Read the reply and prepare a relevant response for review.',
              'outbound_status':'held','untrusted_content':True}
        # Replayed history and later label changes must not reopen or duplicate handled work.
        database.execute('INSERT OR IGNORE INTO reply_tasks VALUES(?,?,?,?,?)',
                         (document['message_id'],kind,'needs_review',json.dumps(task),now()))

    def reply_tasks(self):
        with self.connection() as database:
            return [{**json.loads(row['document']),'kind':row['kind'],'status':row['status'],'created':row['created']}
                    for row in database.execute('SELECT * FROM reply_tasks ORDER BY created DESC LIMIT 200')]

    def dashboard(self):
        with self.connection() as database:
            campaigns = [json.loads(row[0]) for row in database.execute('SELECT document FROM campaigns ORDER BY product')]
            actions = [dict(row) for row in database.execute('SELECT action_key,email,product,day,status,provider_id,gmail_id,error,updated FROM actions ORDER BY updated DESC LIMIT 200')]
            messages = [json.loads(row[0]) for row in database.execute('SELECT document FROM mailbox ORDER BY updated DESC LIMIT 200')]
            contacts={row['email']:json.loads(row['document']) for row in database.execute('SELECT email,document FROM contacts')}
            confirmed={row['email']:dict(row) for row in database.execute('SELECT email,message_id,product FROM interest_confirmations')}
            for message in messages:
                sender=message.get('sender_email','').casefold()
                eligible=(sender in contacts and message.get('direction')=='incoming' and not message.get('is_automated')
                          and not set(message.get('labels',[])) & {'SPAM','TRASH','DRAFT'})
                message['interest_eligible']=eligible
                message['interest_product']=contacts.get(sender,{}).get('product') if eligible else None
                message['interest_confirmed']=eligible and confirmed.get(sender,{}).get('message_id')==message.get('message_id')
            held = [dict(row) for row in database.execute('SELECT email,hold_reasons FROM contacts WHERE hold_reasons<>? ORDER BY updated DESC LIMIT 200', ('[]',))]
            counts = {row[0]:row[1] for row in database.execute('SELECT status,COUNT(*) FROM actions GROUP BY status')}
            event_counts = {row[0]:row[1] for row in database.execute('SELECT event_type,COUNT(*) FROM events GROUP BY event_type')}
            accepted_count=database.execute('SELECT COUNT(*) FROM actions WHERE provider_id IS NOT NULL').fetchone()[0]
        return {'campaigns':campaigns,'actions':actions,'messages':messages,'held_contacts':held,
                'reply_tasks':self.reply_tasks(),
                'delivery_counts':counts,'provider_event_counts':event_counts,'accepted_count':accepted_count,
                'mailbox_status':self.metadata('mailbox_status', {'connected':False,'reason':'Gmail authorization is not configured'}),
                'placement':self.metadata('placement', {'inbox':None,'spam':None,'scope':'No seed observations; prospect placement is unknown'}),
                'campaigns_enabled':False}
