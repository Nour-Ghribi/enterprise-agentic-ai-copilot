"""No commercial API access: diagnose Ollama and run real local E2E only when ready."""

import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from copilot.config import ROOT
from copilot.models import Decision, Query
from copilot.provider import ChatProvider
from copilot.workflow import Engine

CASES = [
    ("contact", "Who is the contact for C003?"),
    ("invoice", "Show the overdue invoice balance for C001."),
    ("contract", "What non-renewal notice is required for C002? Give a PDF citation."),
    (
        "comparison",
        "Compare customers C001 and C004, examine their invoices and contracts, identify renewal risks, and recommend follow-up actions without creating any CRM task.",
    ),
]


def local_provider():
    provider = ChatProvider()
    provider.kind, provider.mode, provider.key = "ollama", "ollama", ""
    provider.model = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
    return provider


def local_case(engine, name, question):
    before = len(engine.store.list_table("tasks"))
    result = engine.run(Query(message=question, execution_mode="hybrid"))
    grounded = result.get("grounded_answer") or {}
    calls = result.get("provider_calls", [])
    real = result.get("execution", {}).get("mode") == "local_ollama" and any(
        c.get("execution") == "local_ollama" for c in calls
    )
    success = (
        real
        and bool(grounded.get("verified_claims"))
        and not grounded.get("abstained")
        and not grounded.get("rejected")
    )
    if name == "contact":
        success = success and any(f["fact_id"] == "CT-C003" for f in grounded.get("verified_claims", []))
    elif name == "invoice":
        success = success and any(f["fact_id"] == "C001:overdue" for f in grounded.get("verified_claims", []))
    elif name == "contract":
        success = success and any(
            f.get("citation") and "60 days" in f["text"] for f in grounded.get("verified_claims", [])
        )
    elif name == "comparison":
        success = (
            success
            and {r["customer_id"]: r["score"] for r in result.get("results", [])} == {"C001": 85, "C004": 40}
            and bool(grounded.get("recommendations"))
            and not result.get("proposals")
        )
    success = bool(success and len(engine.store.list_table("tasks")) == before)
    return {"name": name, "status": "passed" if success else "failed", "run": result}


def approval_case(engine):
    result = engine.run(
        Query(
            message="Analyze renewal risk C001, examine all evidence and prepare suitable follow-up actions.",
            execution_mode="hybrid",
        )
    )
    if (
        result.get("execution", {}).get("mode") != "local_ollama"
        or result["status"] != "awaiting_approval"
        or not result["proposals"]
    ):
        return {
            "name": "approval",
            "status": "failed",
            "run": result,
            "reason": "Real model did not prepare a valid paused proposal",
        }
    if engine.store.list_table("tasks"):
        return {
            "name": "approval",
            "status": "failed",
            "reason": "Task appeared before test reviewer approval",
        }
    fresh = Engine(engine.store.directory)
    try:
        resumed = fresh.decide(
            result["run_id"], Decision(approved=True, actor="Explicit local E2E test reviewer")
        )
        passed = resumed["status"] == "completed" and len(fresh.store.list_table("tasks")) == len(
            result["proposals"]
        )
        return {
            "name": "approval",
            "status": "passed" if passed else "failed",
            "run": resumed,
            "reviewer": "Controlled test approval, not model authorization",
        }
    finally:
        fresh.close()


def check():
    provider = local_provider()
    binary = shutil.which("ollama")
    alternate = Path(os.getenv("LOCALAPPDATA", ".")) / "Programs" / "Ollama" / "ollama.exe"
    if not binary and alternate.is_file():
        binary = str(alternate)
    runtime = provider.ollama_status(refresh=True)
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "ollama_executable": binary,
        "runtime": runtime,
        "commercial_api_used": False,
        "cases": [],
        "external_integrations_tested": False,
    }
    if runtime["status"] != "ready":
        report.update(
            status="blocked_runtime",
            executed=0,
            passed=0,
            failed=0,
            blocked=[name for name, _ in CASES] + ["approval"],
            reason="No inference was executed. Install/start Ollama and pull a local tool-capable model.",
        )
    else:
        # Force mock enterprise data and the local provider, regardless of unrelated environment settings.
        selected = {
            "LLM_MODE": "ollama",
            "LLM_PROVIDER": "ollama",
            "CRM_MODE": "mock",
            "ERP_MODE": "mock",
            "AZURE_FOUNDRY_MODE": "mock",
        }
        previous = {key: os.environ.get(key) for key in selected}
        os.environ.update(selected)
        start = time.perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix="copilot-ollama-e2e-") as temp:
                engine = Engine(Path(temp))
                try:
                    for name, question in CASES:
                        report["cases"].append(record_case(name, lambda: local_case(engine, name, question)))
                    report["cases"].append(record_case("approval", lambda: approval_case(engine)))
                finally:
                    engine.close()
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        passed = sum(case["status"] == "passed" for case in report["cases"])
        report.update(
            status="passed" if passed == len(CASES) + 1 else "failed",
            executed=len(report["cases"]),
            passed=passed,
            failed=len(report["cases"]) - passed,
            total_latency_ms=round((time.perf_counter() - start) * 1000, 2),
        )
    report["inference_verified"] = any(
        call.get("execution") == "local_ollama" and call.get("usage", {}).get("completion_tokens", 0) > 0
        for case in report["cases"]
        for call in case.get("run", {}).get("provider_calls", [])
    )
    target = ROOT / "reports" / "ollama-e2e.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
    return report


def record_case(name, run):
    """Keep a failed scenario in the report and continue the other real checks."""
    try:
        return run()
    except Exception as exc:
        return {"name": name, "status": "failed", "error_type": type(exc).__name__, "error": str(exc)}


def main():
    report = check()
    # Availability checks and skipped scenarios must never satisfy the acceptance gate.
    return 0 if report["status"] == "passed" and report["passed"] == len(CASES) + 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
