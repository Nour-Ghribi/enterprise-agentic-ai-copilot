"""Verify that LangGraph approval survives a Python process exit, using synthetic CRM only."""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHILD = r'''
import json
import sys
from pathlib import Path
from copilot.models import Decision, Query
from copilot.workflow import Engine

engine = Engine(Path(sys.argv[1]))
try:
    phase = sys.argv[2]
    if phase == "prepare":
        run = engine.run(Query(message="Analyze risk and prepare follow-up actions", customer_id="C001"))
        assert run["status"] == "awaiting_approval" and len(run["proposals"]) == 1
        assert engine.store.list_table("tasks") == []
        print(json.dumps({"run_id": run["run_id"], "tasks": 0, "status": run["status"]}))
    elif phase == "approve":
        run = engine.decide(sys.argv[3], Decision(approved=True, actor="Process restart audit reviewer"))
        assert run["status"] == "completed" and len(engine.store.list_table("tasks")) == 1
        print(json.dumps({"status": run["status"], "tasks": 1}))
    else:
        try:
            engine.decide(sys.argv[3], Decision(approved=True, actor="Duplicate test reviewer"))
        except ValueError:
            pass
        else:
            raise AssertionError("Duplicate decision was accepted")
        assert len(engine.store.list_table("tasks")) == 1
        assert any(e["event"] == "human_decision" for e in engine.store.list_table("audit"))
        print(json.dumps({"duplicate_rejected": True, "tasks": 1, "audit_persisted": True}))
finally:
    engine.close()
'''


def main():
    env = {
        **os.environ, "PYTHONUTF8": "1", "LLM_MODE": "offline", "LLM_PROVIDER": "ollama",
        "CRM_MODE": "mock", "ERP_MODE": "mock", "AZURE_FOUNDRY_MODE": "mock", "SEMANTIC_ENABLED": "0",
    }
    with tempfile.TemporaryDirectory(prefix="copilot-approval-restart-") as directory:
        def run(phase, run_id=""):
            process = subprocess.run(
                [sys.executable, "-c", CHILD, directory, phase, run_id],
                cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=90,
            )
            if process.returncode:
                raise RuntimeError(f"Approval {phase} failed: {process.stderr[-2000:]}")
            return json.loads(process.stdout)

        prepared = run("prepare")
        approved = run("approve", prepared["run_id"])
        duplicate = run("duplicate", prepared["run_id"])
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(), "status": "passed",
        "separate_processes": 3, "llm_used": False, "crm": "synthetic",
        "prepared": prepared, "approved": approved, "duplicate": duplicate,
    }
    (ROOT / "reports" / "approval-restart.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
