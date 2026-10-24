"""Exercise Streamlit against a real isolated FastAPI HTTP server, including human review controls."""

import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from copilot.api import create_app  # noqa: E402


def button(app, label):
    return next(b for b in app.button if b.label == label)


def field(app, label):
    return next(f for f in app.text_input if f.label == label)


def check(app):
    assert not app.exception, [e.message for e in app.exception]


def fixture_agent(request):
    """Explicit HTTP test double, never a real model or evaluation score."""
    body = json.loads(request.content)
    observations = [json.loads(m["content"]) for m in body["messages"] if m["role"] == "tool"]
    if not observations:
        calls = []
        for cid in ["C001", "C004"]:
            for name in ["get_customer", "get_invoices", "get_tickets", "search_contracts"]:
                args = {"customer_id": cid}
                if name == "search_contracts":
                    args["query"] = "renewal expiration dispute"
                calls.append(
                    {
                        "id": str(len(calls)),
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                )
        message = {"role": "assistant", "tool_calls": calls}
    else:
        facts = {f["fact_id"]: f for o in observations for f in o.get("facts", [])}
        claims = [
            {k: facts[i][k] for k in ("fact_id", "customer_id", "text")} for i in ["C001:score", "C004:score"]
        ]
        message = {
            "role": "assistant",
            "content": json.dumps(
                {
                    "claims": claims,
                    "recommendations": [
                        {
                            "customer_id": "C001",
                            "action": "payment_plan",
                            "based_on": ["C001:overdue"],
                            "priority": "urgent",
                        },
                        {
                            "customer_id": "C004",
                            "action": "legal_review",
                            "based_on": ["CON-C004:dispute"],
                            "priority": "normal",
                        },
                    ],
                }
            ),
        }
    return httpx.Response(
        200,
        json={
            "model": "UI-scripted-fixture",
            "choices": [{"message": message}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        },
    )


def main():
    os.environ["LLM_MODE"] = "offline"
    os.environ["APPROVAL_TOKEN"] = "ui-smoke-review-token"
    with tempfile.TemporaryDirectory(prefix="copilot-ui-") as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        os.environ["COPILOT_API_URL"] = base
        os.environ["COPILOT_PUBLIC_API_URL"] = base
        api = create_app(Path(directory))
        server = uvicorn.Server(uvicorn.Config(api, host="127.0.0.1", port=port, log_level="error"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    if httpx.get(base + "/health", timeout=1).status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Isolated backend did not start")
            app = AppTest.from_file(str(ROOT / "dashboard.py"), default_timeout=60).run()
            check(app)
            assert len(app.tabs) == 6
            button(app, "Run renewal-risk demo").click().run()
            check(app)
            run = app.session_state["copilot_run"]
            assert run["status"] == "awaiting_approval"
            proposal_count = len(run["proposals"])
            assert proposal_count > 0
            assert httpx.get(base + "/tasks").json() == []
            field(app, "Reviewer name").set_value("Synthetic UI reviewer")
            field(app, "Approval token").set_value("ui-smoke-review-token")
            next(c for c in app.checkbox if c.label.startswith("I reviewed")).check()
            button(app, "Approve batch & create mock CRM tasks").click().run()
            check(app)
            tasks = httpx.get(base + "/tasks").json()
            assert len(tasks) == proposal_count
            assert app.session_state["copilot_run"]["status"] == "completed"
            button(app, "Who is the contact for C003?").click().run()
            check(app)
            assert [s["agent"] for s in app.session_state["copilot_run"]["trace"]] == [
                "supervisor",
                "crm",
                "answer",
            ]
            next(s for s in app.selectbox if s.label == "Execution mode").set_value("hybrid")
            button(app, "Compare C001 and C004 — recommendations only").click().run()
            check(app)
            comparison = app.session_state["copilot_run"]
            assert comparison["customer_ids"] == ["C001", "C004"]
            assert not comparison["proposals"]
            assert len(httpx.get(base + "/tasks").json()) == proposal_count
            api.state.engine.provider.mode = "openai"
            api.state.engine.provider.key = "explicit-ui-fixture-key"
            api.state.engine.provider.model = "UI-scripted-fixture"
            api.state.engine.provider.transport = httpx.MockTransport(fixture_agent)
            button(app, "Compare C001 and C004 — recommendations only").click().run()
            check(app)
            simulated = app.session_state["copilot_run"]
            assert simulated["execution"]["mode"] == "simulated_provider"
            assert len(simulated["grounded_answer"]["verified_claims"]) == 2
            assert len(simulated["tool_calls"]) == 8 and not simulated["proposals"]
            report = {
                "initial_render": True,
                "tabs": [t.label for t in app.tabs],
                "main_demo_paused": True,
                "review_form_resumed_graph": True,
                "persisted_mock_tasks": len(tasks),
                "ordinary_lookup_agents": ["supervisor", "crm", "answer"],
                "phase2_comparison_customers": comparison["customer_ids"],
                "phase2_no_additional_task": True,
                "phase2_execution": comparison.get("execution"),
                "phase2_simulated_agent_ui": {
                    "execution": simulated["execution"]["mode"],
                    "tools": 8,
                    "claims": 2,
                },
                "exceptions": 0,
                "database": "isolated temporary synthetic workspace",
            }
            (ROOT / "reports" / "ui-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
        finally:
            server.should_exit = True
            thread.join(timeout=15)


if __name__ == "__main__":
    main()
