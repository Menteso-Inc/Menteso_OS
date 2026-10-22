"""Transactional content/approval queue. Provider identifiers stay in .env."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .models import Draft


class Store:
    def __init__(self, directory):
        if directory.is_symlink(): raise ValueError('State directory cannot be linked')
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory/'social.sqlite3'
        if self.path.is_symlink(): raise ValueError('State database cannot be linked')
        with self.connection() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS posts(key TEXT PRIMARY KEY,data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,created TEXT NOT NULL,status TEXT NOT NULL);''')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(str(self.path),timeout=5)
        try:
            with db: yield db
        finally: db.close()

    def install(self, drafts):
        with self.connection() as db:
            for draft in drafts:
                draft=draft.model_copy(update={'created_at':draft.created_at or datetime.now(timezone.utc)})
                db.execute('INSERT OR IGNORE INTO posts VALUES (?,?)',(draft.key,draft.model_dump_json()))

    def list(self):
        with self.connection() as db:
            return [Draft.model_validate_json(row[0]) for row in db.execute('SELECT data FROM posts ORDER BY key')]

    def get(self, key):
        with self.connection() as db: row=db.execute('SELECT data FROM posts WHERE key=?',(key,)).fetchone()
        if not row: raise KeyError('Draft not found')
        return Draft.model_validate_json(row[0])

    def update(self, key, revision, change):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT data FROM posts WHERE key=?',(key,)).fetchone()
            if not row: raise KeyError('Draft not found')
            draft=Draft.model_validate_json(row[0])
            if draft.revision!=revision: raise ValueError('Draft changed; refresh before updating')
            if draft.status in {'publishing','processing','uploaded','published','needs_reconciliation'}:
                raise ValueError('Publication must be reconciled before this draft can change')
            draft=change(draft)
            draft=Draft.model_validate(draft.model_dump())
            db.execute('UPDATE posts SET data=? WHERE key=?',(draft.model_dump_json(),key))
            return draft

    def claim(self, key, cap):
        now=datetime.now(timezone.utc)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT data FROM posts WHERE key=?',(key,)).fetchone()
            if not row: raise KeyError('Draft not found')
            draft=Draft.model_validate_json(row[0])
            if draft.status!='scheduled' or not draft.scheduled_at or draft.scheduled_at>now:
                raise ValueError('No approved publication is due')
            if draft.approval_digest!=draft.digest(): raise ValueError('Content approval is stale')
            count=db.execute('SELECT count(*) FROM attempts WHERE created>=?',(now.date().isoformat(),)).fetchone()[0]
            if count>=cap: raise ValueError('Daily publication ceiling reached')
            if db.execute('SELECT 1 FROM attempts WHERE key=?',(key,)).fetchone():
                raise ValueError('A previous publication attempt requires reconciliation; never repeat it automatically')
            # One attempt per exact draft; ambiguous writes are never repeated.
            db.execute('INSERT INTO attempts VALUES (?,?,?)',(key,now.isoformat(),'publishing'))
            draft.status='publishing'
            db.execute('UPDATE posts SET data=? WHERE key=?',(draft.model_dump_json(),key))
            return draft

    def finish(self, key, status, note='', receipt_key=None):
        if status not in {'processing','uploaded','published','needs_reconciliation','failed'}: raise ValueError('Invalid publication outcome')
        with self.connection() as db:
            row=db.execute('SELECT data FROM posts WHERE key=?',(key,)).fetchone()
            if not row: raise KeyError('Draft not found')
            draft=Draft.model_validate_json(row[0]); draft.status=status; draft.note=note[:500]; draft.receipt_key=receipt_key
            if status=='published' and draft.published_at is None:
                draft.published_at=datetime.now(timezone.utc)
            db.execute('UPDATE posts SET data=? WHERE key=?',(draft.model_dump_json(),key))
            db.execute('UPDATE attempts SET status=? WHERE key=?',(status,key))

    def metadata(self, key, value=None):
        with self.connection() as db:
            if value is not None:
                db.execute('INSERT INTO metadata VALUES (?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data',(key,json.dumps(value)))
                return value
            row=db.execute('SELECT data FROM metadata WHERE key=?',(key,)).fetchone()
            return json.loads(row[0]) if row else {}

    def recover_interrupted(self):
        # A dead process may have published before losing its receipt. Never
        # turn an interrupted publishing state back into a runnable job.
        for draft in self.list():
            if draft.status=='publishing':
                self.finish(draft.key,'needs_reconciliation','Worker was interrupted; check the platform before any retry')

    def purge_youtube_authorized_data(self):
        """Remove provider cache/receipt references while preserving authored work and duplicate guards."""
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT data FROM metadata WHERE key=?',('connections',)).fetchone()
            if row:
                cached=json.loads(row[0]);cached.get('platforms',{}).pop('youtube',None)
                db.execute('UPDATE metadata SET data=? WHERE key=?',(json.dumps(cached),'connections'))
            for key in ('api_backoff_youtube','processing_blocker'):
                db.execute('DELETE FROM metadata WHERE key=?',(key,))
            row=db.execute('SELECT data FROM metadata WHERE key=?',('oauth_result',)).fetchone()
            if row and json.loads(row[0]).get('platform')=='youtube':
                db.execute('DELETE FROM metadata WHERE key=?',('oauth_result',))
            for key,raw in db.execute('SELECT key,data FROM posts').fetchall():
                draft=Draft.model_validate_json(raw)
                if draft.platform!='youtube':continue
                draft.receipt_key=None
                if draft.status in {'scheduled','approved'}:
                    draft.status='paused';draft.scheduled_at=None;draft.approval_digest=None;draft.revision+=1
                if draft.status in {'publishing','processing'}:
                    draft.status='needs_reconciliation';draft.note='Disconnected. Check YouTube before any further upload.'
                db.execute('UPDATE posts SET data=? WHERE key=?',(draft.model_dump_json(),key))
