"""Exercise existing Streamlit demos with actual Ollama, isolated synthetic data and explicit review."""

import json
import os
import socket
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from smoke_ui import ROOT, AppTest, button, check, create_app, field, httpx, uvicorn


def main():
    os.environ.update({
        "LLM_MODE": "ollama", "LLM_PROVIDER": "ollama", "CRM_MODE": "mock", "ERP_MODE": "mock",
        "AZURE_FOUNDRY_MODE": "mock", "APPROVAL_TOKEN": "ollama-ui-audit-reviewer",
    })
    with tempfile.TemporaryDirectory(prefix="copilot-real-ui-") as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        os.environ["COPILOT_API_URL"] = os.environ["COPILOT_PUBLIC_API_URL"] = base
        api = create_app(Path(directory))
        assert api.state.engine.provider.ollama_status(refresh=True)["status"] == "ready"
        assert api.state.engine.provider.transport is None
        server = uvicorn.Server(uvicorn.Config(api, host="127.0.0.1", port=port, log_level="error"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(60):
                try:
                    if httpx.get(base + "/health", timeout=2).status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("Isolated backend unavailable")
            app = AppTest.from_file(str(ROOT / "dashboard.py"), default_timeout=660).run()
            check(app)
            next(s for s in app.selectbox if s.label == "Execution mode").set_value("hybrid")
            button(app, "Who is the contact for C003?").click().run()
            check(app)
            contact = app.session_state["copilot_run"]
            assert contact["execution"]["mode"] == "local_ollama"
            assert any(f["fact_id"] == "CT-C003" for f in contact["grounded_answer"]["verified_claims"])
            button(app, "Run renewal-risk demo").click().run()
            check(app)
            proposal = app.session_state["copilot_run"]
            assert proposal["execution"]["mode"] == "local_ollama"
            assert proposal["customer_ids"] == ["C001"]
            assert proposal["status"] == "awaiting_approval" and proposal["proposals"]
            assert httpx.get(base + "/tasks").json() == []
            field(app, "Reviewer name").set_value("Real Ollama UI audit reviewer")
            field(app, "Approval token").set_value("ollama-ui-audit-reviewer")
            next(c for c in app.checkbox if c.label.startswith("I reviewed")).check()
            button(app, "Approve batch & create mock CRM tasks").click().run()
            check(app)
            approved = app.session_state["copilot_run"]
            assert approved["status"] == "completed"
            task_count = len(httpx.get(base + "/tasks").json())
            assert task_count == len(proposal["proposals"])
            button(app, "Compare C001 and C004 — recommendations only").click().run()
            check(app)
            comparison = app.session_state["copilot_run"]
            assert comparison["execution"]["mode"] == "local_ollama"
            assert not comparison["grounded_answer"]["abstained"] and not comparison["proposals"]
            assert {r["customer_id"]: r["score"] for r in comparison["results"]} == {"C001": 85, "C004": 40}
            assert len(httpx.get(base + "/tasks").json()) == task_count
            report = {
                "checked_at_utc": datetime.now(timezone.utc).isoformat(), "status": "passed",
                "provider_simulated": False, "tabs": [t.label for t in app.tabs], "exceptions": 0,
                "contact": contact, "proposal": proposal, "approved": approved, "comparison": comparison,
                "persisted_synthetic_tasks": task_count,
            }
            (ROOT / "reports" / "ui-ollama-smoke.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            print(json.dumps({k: v for k, v in report.items() if k not in {
                "contact", "proposal", "approved", "comparison"
            }}, indent=2))
        finally:
            server.should_exit = True
            thread.join(timeout=15)


if __name__ == "__main__":
    main()
