"""Transactional prospect inventory and query rotation; business data, not memory."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


def targeting_key(request, policy_version):
    fields = ("countries", "target_segments", "buyer_roles", "size_min", "size_max", "small_firm_max", "size_unit")
    values = {field: getattr(request, field) for field in fields}
    values["qualification_policy_version"] = policy_version
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


class ProspectStore:
    def __init__(self, directory):
        directory = Path(directory)
        if directory.is_symlink():
            raise ValueError("Prospect inventory cannot use a linked directory")
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "prospects.sqlite3"
        if self.path.is_symlink():
            raise ValueError("Prospect inventory cannot use a linked database")
        with self._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS firms (
                    mode TEXT NOT NULL, domain TEXT NOT NULL, profile TEXT NOT NULL,
                    data TEXT NOT NULL, PRIMARY KEY (mode, domain));
                CREATE TABLE IF NOT EXISTS observations (
                    mode TEXT NOT NULL, run_id TEXT NOT NULL, domain TEXT NOT NULL,
                    data TEXT NOT NULL, PRIMARY KEY (mode, run_id, domain));
                CREATE TABLE IF NOT EXISTS queries (
                    profile TEXT NOT NULL, query TEXT NOT NULL, used INTEGER NOT NULL,
                    last_use INTEGER NOT NULL, PRIMARY KEY (profile, query));
                CREATE TABLE IF NOT EXISTS reservations (
                    profile TEXT NOT NULL, run_id TEXT NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY (profile, run_id));
                CREATE TABLE IF NOT EXISTS source_holds (
                    host TEXT PRIMARY KEY, reason TEXT NOT NULL,
                    retry_at REAL, observed_at REAL NOT NULL);
            """)

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(str(self.path), timeout=5)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def reserve_queries(self, profile, run_id, queries, limit):
        queries = list(dict.fromkeys(queries))
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT data FROM reservations WHERE profile=? AND run_id=?", (profile, run_id)).fetchone()
            if previous:
                return json.loads(previous[0])
            history = {row[0]: (row[1], row[2]) for row in db.execute("SELECT query, used, last_use FROM queries WHERE profile=?", (profile,))}
            selected = sorted(queries, key=lambda query: (*history.get(query, (0, 0)), queries.index(query)))[:limit]
            sequence = max((value[1] for value in history.values()), default=0)
            for query in selected:
                sequence += 1
                db.execute("INSERT INTO queries VALUES (?, ?, 1, ?) ON CONFLICT(profile, query) DO UPDATE SET used=used+1, last_use=excluded.last_use", (profile, query, sequence))
            db.execute("INSERT INTO reservations VALUES (?, ?, ?)", (profile, run_id, json.dumps(selected)))
            return selected

    def source_hold(self, host):
        """Holds survive runs/restarts; a rate limit expires, an access denial does not."""
        with self._connection() as db:
            row = db.execute("SELECT reason, retry_at FROM source_holds WHERE host=?", (host,)).fetchone()
        if row and (row[1] is None or row[1] > time.time()):
            return row[0]
        return None

    def hold_source(self, host, reason, retry_at=None):
        with self._connection() as db:
            # Parallel runs cannot downgrade an indefinite review hold or
            # shorten a pause already observed by another worker.
            db.execute("""INSERT INTO source_holds VALUES (?, ?, ?, ?) ON CONFLICT(host) DO UPDATE SET
                reason=CASE WHEN source_holds.retry_at IS NULL THEN source_holds.reason ELSE excluded.reason END,
                retry_at=CASE WHEN source_holds.retry_at IS NULL OR excluded.retry_at IS NULL THEN NULL ELSE MAX(source_holds.retry_at, excluded.retry_at) END,
                observed_at=excluded.observed_at""",
                       (host, reason[:1000], retry_at, time.time()))

    def release_source_hold(self, host):
        """Operator-only recovery after reviewing the cause; never called by retries."""
        with self._connection() as db:
            db.execute("DELETE FROM source_holds WHERE host=?", (host,))

    def save(self, profile, run_id, record):
        from agents.prospect_research_agent.models import FirmRecord
        record = FirmRecord.model_validate(record)
        payload = record.model_dump()
        data = json.dumps(payload, ensure_ascii=False)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO observations VALUES (?, ?, ?, ?) ON CONFLICT(mode, run_id, domain) DO UPDATE SET data=excluded.data", (record.provenance, run_id, record.domain, data))
            previous = db.execute("SELECT profile, data FROM firms WHERE mode=? AND domain=?", (record.provenance, record.domain)).fetchone()
            if previous and previous[0] == profile:
                old = json.loads(previous[1])
                # A failed refresh must not destroy a better sourced observation.
                def quality(row):
                    return (row.get("fit_status") == "qualified", len(row.get("evidence", [])), len(row.get("contacts", [])))
                if quality(old) > quality(payload):
                    return
            db.execute("INSERT INTO firms VALUES (?, ?, ?, ?) ON CONFLICT(mode, domain) DO UPDATE SET profile=excluded.profile, data=excluded.data", (record.provenance, record.domain, profile, data))

    def records(self, profile, mode="live", limit=500):
        from agents.prospect_research_agent.models import FirmRecord
        with self._connection() as db:
            rows = db.execute("SELECT data FROM firms WHERE profile=? AND mode=? ORDER BY domain LIMIT ?", (profile, mode, min(max(limit, 1), 500)))
            return [FirmRecord.model_validate(json.loads(row[0])).model_dump() for row in rows]
