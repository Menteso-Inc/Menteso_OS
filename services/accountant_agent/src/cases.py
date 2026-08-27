"""Persistent accounting conversation cases keyed by Gmail thread ID."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from typing import Optional, Protocol


@dataclass
class AccountingCase:
    thread_id: str
    pid: str
    requester_email: str
    requester_name: str
    state: str
    company_key: str
    zoho_record_id: str
    spec: dict
    question: str = ""
    wave_invoice_id: str = ""
    invoice_number: str = ""
    updated_at: int = 0


class CaseStore(Protocol):
    def get(self, thread_id: str) -> Optional[AccountingCase]: ...
    def save(self, case: AccountingCase) -> None: ...


class InMemoryCaseStore:
    def __init__(self):
        self.cases: dict[str, AccountingCase] = {}

    def get(self, thread_id: str) -> Optional[AccountingCase]:
        return self.cases.get(thread_id)

    def save(self, case: AccountingCase) -> None:
        case.updated_at = int(time.time())
        self.cases[case.thread_id] = case


class SQLiteCaseStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS accounting_cases (
                    thread_id TEXT PRIMARY KEY,
                    pid TEXT NOT NULL,
                    requester_email TEXT NOT NULL,
                    requester_name TEXT NOT NULL,
                    state TEXT NOT NULL,
                    company_key TEXT NOT NULL,
                    zoho_record_id TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    question TEXT NOT NULL DEFAULT '',
                    wave_invoice_id TEXT NOT NULL DEFAULT '',
                    invoice_number TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL
                )"""
            )

    def _connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def get(self, thread_id: str) -> Optional[AccountingCase]:
        with self._connect() as db:
            row = db.execute(
                """SELECT thread_id,pid,requester_email,requester_name,state,
                          company_key,zoho_record_id,spec_json,question,
                          wave_invoice_id,invoice_number,updated_at
                   FROM accounting_cases WHERE thread_id=?""",
                (thread_id,),
            ).fetchone()
        if not row:
            return None
        return AccountingCase(
            thread_id=row[0], pid=row[1], requester_email=row[2],
            requester_name=row[3], state=row[4], company_key=row[5],
            zoho_record_id=row[6], spec=json.loads(row[7]), question=row[8],
            wave_invoice_id=row[9], invoice_number=row[10], updated_at=row[11],
        )

    def save(self, case: AccountingCase) -> None:
        case.updated_at = int(time.time())
        with self._connect() as db:
            db.execute(
                """INSERT INTO accounting_cases(
                       thread_id,pid,requester_email,requester_name,state,
                       company_key,zoho_record_id,spec_json,question,
                       wave_invoice_id,invoice_number,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(thread_id) DO UPDATE SET
                       pid=excluded.pid, requester_email=excluded.requester_email,
                       requester_name=excluded.requester_name, state=excluded.state,
                       company_key=excluded.company_key,
                       zoho_record_id=excluded.zoho_record_id,
                       spec_json=excluded.spec_json, question=excluded.question,
                       wave_invoice_id=excluded.wave_invoice_id,
                       invoice_number=excluded.invoice_number,
                       updated_at=excluded.updated_at""",
                (
                    case.thread_id, case.pid, case.requester_email,
                    case.requester_name, case.state, case.company_key,
                    case.zoho_record_id, json.dumps(case.spec, ensure_ascii=False),
                    case.question, case.wave_invoice_id, case.invoice_number,
                    case.updated_at,
                ),
            )


def build_case_store(in_memory: bool = False) -> CaseStore:
    if in_memory:
        return InMemoryCaseStore()
    return SQLiteCaseStore(os.environ.get(
        "CASE_DB_PATH", "/home/menteso_os/data/accountant_agent/cases.sqlite3"
    ))
