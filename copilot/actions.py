import hashlib
import json
import uuid

from copilot.models import Decision
from copilot.store import Store


def propose(store: Store, run_id: str, results: list[dict]) -> list[dict]:
    proposals = []
    with store.connect() as db:
        for result in results:
            if result["score"] < 25 or result["warnings"]:
                continue  # Missing evidence requires investigation before a business action.
            fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        "customer": result["customer_id"],
                        "as_of": result["as_of"],
                        "signals": result["signals"],
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            existing = db.execute("SELECT id FROM tasks WHERE fingerprint=?", (fingerprint,)).fetchone()
            if existing:
                continue
            pid = str(uuid.uuid5(uuid.NAMESPACE_URL, run_id + fingerprint))
            action = {
                "id": pid,
                "run_id": run_id,
                "customer_id": result["customer_id"],
                "subject": f"Renewal review - {result['customer']}",
                "description": " ".join(result["suggested_actions"]),
                "score": result["score"],
                "evidence": result["signals"],
                "status": "pending",
                "fingerprint": fingerprint,
                "target": "synthetic_mock_crm",
            }
            db.execute(
                "INSERT OR IGNORE INTO proposals VALUES(?,?,?,?,?,?)",
                (pid, run_id, result["customer_id"], fingerprint, "pending", json.dumps(action)),
            )
            proposals.append(action)
        if proposals:
            Store.audit(
                db, "actions_proposed", {"run_id": run_id, "proposal_ids": [p["id"] for p in proposals]}
            )
    return proposals


def apply_decision(store: Store, run_id: str, proposal_ids: list[str], decision: Decision) -> list[dict]:
    """Atomic approval + mock mutation + audit; never called by a language model or retrieval tool."""
    outcomes = []
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for pid in proposal_ids:
            row = db.execute("SELECT * FROM proposals WHERE id=? AND run_id=?", (pid, run_id)).fetchone()
            if row is None:
                raise ValueError("Proposal does not belong to this workflow")
            if row["status"] != "pending":
                outcomes.append({"proposal_id": pid, "status": row["status"], "idempotent_replay": True})
                continue
            action = json.loads(row["data"])
            task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, action["fingerprint"]))
            status = "rejected"
            if decision.approved:
                task = {
                    "id": task_id,
                    "proposal_id": pid,
                    "customer_id": action["customer_id"],
                    "subject": action["subject"],
                    "description": action["description"],
                    "approved_by": decision.actor,
                    "approval_note": decision.note,
                    "synthetic": True,
                }
                inserted = db.execute(
                    "INSERT OR IGNORE INTO tasks VALUES(?,?,?,?)",
                    (task_id, pid, row["fingerprint"], json.dumps(task)),
                ).rowcount
                status = "executed" if inserted else "duplicate_prevented"
            db.execute("UPDATE proposals SET status=? WHERE id=?", (status, pid))
            outcome = {
                "proposal_id": pid,
                "status": status,
                "task_id": task_id if decision.approved else None,
            }
            outcomes.append(outcome)
            Store.audit(db, "human_decision", {"run_id": run_id, **decision.model_dump(), **outcome})
    return outcomes
