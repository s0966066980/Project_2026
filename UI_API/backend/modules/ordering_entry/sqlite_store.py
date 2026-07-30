from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .module import EntryFlowError

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS ordering_entry_flows(tenant_id TEXT NOT NULL,store_id TEXT NOT NULL,device_id TEXT NOT NULL,entry_flow_id TEXT NOT NULL,state TEXT NOT NULL,phase_revision INTEGER NOT NULL,policy_version TEXT NOT NULL,policy_result TEXT NOT NULL,policy_snapshot_json TEXT NOT NULL,ordering_session_id TEXT NOT NULL DEFAULT '',member_ref TEXT NOT NULL DEFAULT '',safe_reason TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,completed_at TEXT,PRIMARY KEY(tenant_id,store_id,entry_flow_id));
CREATE UNIQUE INDEX IF NOT EXISTS one_active_entry_flow_per_device ON ordering_entry_flows(tenant_id,store_id,device_id) WHERE state NOT IN ('menu_ready','abandoned');
CREATE TABLE IF NOT EXISTS ordering_sessions(tenant_id TEXT NOT NULL,store_id TEXT NOT NULL,ordering_session_id TEXT NOT NULL,entry_flow_id TEXT NOT NULL,status TEXT NOT NULL,member_ref TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,closed_at TEXT,PRIMARY KEY(tenant_id,store_id,ordering_session_id),UNIQUE(tenant_id,store_id,entry_flow_id));
CREATE TABLE IF NOT EXISTS ordering_entry_events(tenant_id TEXT NOT NULL,store_id TEXT NOT NULL,entry_flow_id TEXT NOT NULL,phase_revision INTEGER NOT NULL,event_type TEXT NOT NULL,payload_json TEXT NOT NULL,occurred_at TEXT NOT NULL,PRIMARY KEY(tenant_id,store_id,entry_flow_id,phase_revision));
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


class SQLiteEntryFlowStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self._connect() as c:
            c.executescript(SCHEMA)

    def _connect(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    @contextmanager
    def tx(self):
        c = self._connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def start(
        self, *, scope, entry_flow_id, policy_version, policy_result, policy_snapshot, initial_state, create_session
    ):
        t, s, d = str(scope.tenant_id), str(scope.store_id), str(scope.device_id)
        now = _now()
        with self.tx() as c:
            row = c.execute(
                "SELECT * FROM ordering_entry_flows WHERE tenant_id=? AND store_id=? AND device_id=? AND state NOT IN ('menu_ready','abandoned')",
                (t, s, d),
            ).fetchone()
            if row:
                return self._row(row)
            fid = entry_flow_id or str(uuid4())
            sid = str(uuid4()) if create_session else ""
            c.execute(
                "INSERT INTO ordering_entry_flows(tenant_id,store_id,device_id,entry_flow_id,state,phase_revision,policy_version,policy_result,policy_snapshot_json,ordering_session_id,member_ref,safe_reason,created_at,updated_at,completed_at) VALUES(?,?,?,?,?,1,?,?,?,?,?,?,?,?,NULL)",
                (
                    t,
                    s,
                    d,
                    fid,
                    initial_state,
                    policy_version,
                    policy_result,
                    json.dumps(policy_snapshot, separators=(",", ":")),
                    sid,
                    "",
                    "",
                    now,
                    now,
                ),
            )
            if sid:
                c.execute("INSERT INTO ordering_sessions VALUES(?,?,?,?, 'open','',?,NULL)", (t, s, sid, fid, now))
            c.execute(
                "INSERT INTO ordering_entry_events VALUES(?,?,?,?, 'started',?,?)",
                (t, s, fid, 1, json.dumps({"state": initial_state}, separators=(",", ":")), now),
            )
        return self.get(scope=scope, entry_flow_id=fid)

    def get(self, *, scope, entry_flow_id):
        with self._connect() as c:
            r = c.execute(
                "SELECT * FROM ordering_entry_flows WHERE tenant_id=? AND store_id=? AND entry_flow_id=?",
                (str(scope.tenant_id), str(scope.store_id), entry_flow_id),
            ).fetchone()
        if not r:
            raise EntryFlowError("entry_flow_not_found")
        return self._row(r)

    def command(self, *, scope, entry_flow_id, expected_revision, target, command, payload, effects):
        t, s = str(scope.tenant_id), str(scope.store_id)
        now = _now()
        with self.tx() as c:
            r = c.execute(
                "SELECT * FROM ordering_entry_flows WHERE tenant_id=? AND store_id=? AND entry_flow_id=?",
                (t, s, entry_flow_id),
            ).fetchone()
            if not r:
                raise EntryFlowError("entry_flow_not_found")
            if int(r["phase_revision"]) != int(expected_revision):
                raise EntryFlowError(
                    "entry_flow_revision_conflict", details={"current_revision": int(r["phase_revision"])}
                )
            sid = r["ordering_session_id"]
            member_ref = str(payload.get("member_ref") or r["member_ref"] or "")
            if any(e["type"] == "ensure_ordering_session" for e in effects) and not sid:
                sid = str(uuid4())
                c.execute(
                    "INSERT INTO ordering_sessions VALUES(?,?,?,?, 'open',?,?,NULL)",
                    (t, s, sid, entry_flow_id, member_ref, now),
                )
            rev = int(r["phase_revision"]) + 1
            completed = now if target in ("menu_ready", "abandoned") else None
            c.execute(
                "UPDATE ordering_entry_flows SET state=?,phase_revision=?,ordering_session_id=?,member_ref=?,safe_reason=?,updated_at=?,completed_at=? WHERE tenant_id=? AND store_id=? AND entry_flow_id=?",
                (
                    target,
                    rev,
                    sid,
                    member_ref,
                    str(payload.get("safe_reason") or "")[:160],
                    now,
                    completed,
                    t,
                    s,
                    entry_flow_id,
                ),
            )
            if target == "abandoned" and sid:
                c.execute(
                    "UPDATE ordering_sessions SET status='abandoned',closed_at=? WHERE tenant_id=? AND store_id=? AND ordering_session_id=? AND status='open'",
                    (now, t, s, sid),
                )
            c.execute(
                "INSERT INTO ordering_entry_events VALUES(?,?,?,?,?,?,?)",
                (
                    t,
                    s,
                    entry_flow_id,
                    rev,
                    command,
                    json.dumps({"target": target, "effects": effects}, separators=(",", ":")),
                    now,
                ),
            )
        return self.get(scope=scope, entry_flow_id=entry_flow_id)

    @staticmethod
    def _row(r):
        return {
            "entry_flow_id": r["entry_flow_id"],
            "state": r["state"],
            "phase_revision": int(r["phase_revision"]),
            "policy_version": r["policy_version"],
            "policy_result": r["policy_result"],
            "policy_snapshot": r["policy_snapshot_json"]
            if isinstance(r["policy_snapshot_json"], dict)
            else json.loads(r["policy_snapshot_json"]),
            "ordering_session_id": r["ordering_session_id"],
            "member_ref": r["member_ref"],
            "safe_reason": r["safe_reason"],
        }
