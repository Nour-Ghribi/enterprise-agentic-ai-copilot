"""Run one real, read-only provider demonstration when credentials are configured."""

import json
import tempfile
from pathlib import Path

from copilot.config import ROOT
from copilot.models import Query
from copilot.provider import ChatProvider
from copilot.workflow import Engine

MAIN_DEMO = (
    "Compare customers C001 and C004, examine their invoices and contracts, identify renewal risks, "
    "and recommend follow-up actions without creating any CRM task."
)


def validate():
    provider = ChatProvider()
    report = {
        "provider": provider.kind,
        "requested_model": provider.model,
        "status": "pending_credentials",
        "provider_contacted": False,
    }
    local_unavailable = provider.is_ollama and provider.ollama_status(refresh=True)["status"] != "ready"
    if local_unavailable:
        report.update(
            status="pending_ollama_runtime", runtime=provider.ollama_status(), commercial_api_used=False
        )
    if provider.configured and not local_unavailable:
        with tempfile.TemporaryDirectory(prefix="copilot-provider-check-") as temp:
            engine = Engine(Path(temp))
            try:
                result = engine.run(Query(message=MAIN_DEMO, execution_mode="hybrid"))
                calls = result.get("provider_calls", [])
                report = {
                    **report,
                    "status": "completed"
                    if result.get("grounded_answer", {}).get("verified_claims")
                    and not result.get("grounded_answer", {}).get("abstained")
                    else "incomplete",
                    "provider_contacted": bool(calls),
                    "run": result,
                    "no_crm_task_created": not engine.store.list_table("tasks"),
                }
            finally:
                engine.close()
    target = ROOT / "reports" / "provider-validation.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "run"}, indent=2))
    return report


if __name__ == "__main__":
    validate()
