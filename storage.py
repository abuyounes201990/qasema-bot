import os
import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import List

class Storage:
    def __init__(self, db_path: str = "data/bot.db", expire_days: int = 2):
        self.db_path = db_path
        self.expire_days = expire_days
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    @staticmethod
    def fingerprint(lines: List[str]) -> str:
        h = hashlib.sha256()
        for ln in lines:
            h.update((ln + "\n").encode("utf-8"))
        return h.hexdigest()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as con:
            cur = con.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS slips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    raw_text TEXT,
                    fingerprint TEXT,
                    created_at TEXT
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slip_id INTEGER,
                    norm_pair TEXT,
                    active INTEGER DEFAULT 1,
                    created_at TEXT,
                    FOREIGN KEY(slip_id) REFERENCES slips(id)
                )
            ''')
            con.commit()

    def set_expire_days(self, days: int):
        self.expire_days = max(0, days)

    def slip_fingerprint_exists(self, fingerprint: str) -> bool:
        with self._conn() as con:
            cur = con.cursor()
            cur.execute("SELECT 1 FROM slips WHERE fingerprint = ? LIMIT 1", (fingerprint,))
            return cur.fetchone() is not None

    def save_slip(self, user_id: int, raw_text: str, fingerprint: str) -> int:
        with self._conn() as con:
            cur = con.cursor()
            cur.execute(
                "INSERT INTO slips (user_id, raw_text, fingerprint, created_at) VALUES (?, ?, ?, ?)",
                (user_id, raw_text, fingerprint, datetime.utcnow().isoformat()),
            )
            con.commit()
            return cur.lastrowid

    def save_matches(self, slip_id: int, norm_pairs: List[str]):
        with self._conn() as con:
            cur = con.cursor()
            for p in norm_pairs:
                cur.execute(
                    "INSERT INTO matches (slip_id, norm_pair, active, created_at) VALUES (?, ?, 1, ?)",
                    (slip_id, p, datetime.utcnow().isoformat())
                )
            con.commit()

    def pair_exists_active(self, norm_pair: str) -> bool:
        with self._conn() as con:
            cur = con.cursor()
            cur.execute("SELECT 1 FROM matches WHERE norm_pair = ? AND active = 1 LIMIT 1", (norm_pair,))
            return cur.fetchone() is not None

    def expire_old_matches(self):
        if self.expire_days <= 0:
            return
        cutoff = datetime.utcnow() - timedelta(days=self.expire_days)
        with self._conn() as con:
            cur = con.cursor()
            cur.execute(
                "UPDATE matches SET active = 0 WHERE active = 1 AND datetime(created_at) < datetime(?)",
                (cutoff.isoformat(),)
            )
            con.commit()
