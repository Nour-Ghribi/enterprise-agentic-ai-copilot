import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class Store:
    collections = {"contracts", "invoices", "tickets", "opportunities", "interactions", "contacts", "orders"}

    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "business.sqlite"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS customers(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS records(
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, customer_id TEXT NOT NULL REFERENCES customers(id),
                    data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS record_lookup ON records(kind, customer_id);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS proposals(
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, customer_id TEXT NOT NULL REFERENCES customers(id),
                    fingerprint TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks(
                    id TEXT PRIMARY KEY, proposal_id TEXT UNIQUE NOT NULL REFERENCES proposals(id),
                    fingerprint TEXT UNIQUE NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, event TEXT NOT NULL, data TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def customers(self, search: str = "") -> list[dict]:
        with self.connect() as db:
            rows = [json.loads(r[0]) for r in db.execute("SELECT data FROM customers ORDER BY id")]
        return [r for r in rows if search.casefold() in (r["name"] + " " + r["id"]).casefold()]

    def customer(self, customer_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT data FROM customers WHERE id=?", (customer_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown customer {customer_id}")
        return json.loads(row[0])

    def records(self, kind: str, customer_id: str | None = None) -> list[dict]:
        if kind not in self.collections:
            raise ValueError("Unknown collection")
        sql, args = "SELECT data FROM records WHERE kind=?", [kind]
        if customer_id:
            sql += " AND customer_id=?"
            args.append(customer_id)
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(sql + " ORDER BY id", args)]

    @staticmethod
    def audit(db, event: str, data: dict):
        db.execute(
            "INSERT INTO audit(at,event,data) VALUES(?,?,?)",
            (datetime.now(timezone.utc).isoformat(), event, json.dumps(data)),
        )

    def list_table(self, table: str) -> list[dict]:
        if table not in {"proposals", "tasks", "audit", "runs"}:
            raise ValueError("Unsupported table")
        with self.connect() as db:
            rows = db.execute(f"SELECT * FROM {table}").fetchall()
        if table == "audit":
            return [{**dict(r), "data": json.loads(r["data"])} for r in rows]
        return [
            {**json.loads(r["data"]), **({"status": r["status"]} if table == "proposals" else {})}
            for r in rows
        ]

    def save_run(self, run_id: str, data: dict):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO runs VALUES(?,?)", (run_id, json.dumps(data)))

    def run(self, run_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError("Run not found")
        return json.loads(row[0])
