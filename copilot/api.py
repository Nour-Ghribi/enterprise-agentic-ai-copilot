import json
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Query as Param
from fastapi.responses import FileResponse

from copilot.config import AS_OF, DATA, ROOT, OFFLINE_LABEL, approval_token
from copilot.models import Decision, Query, Search
from copilot.workflow import Engine
from copilot.integrations import IntegrationUnavailable


def create_app(directory=DATA):
    @asynccontextmanager
    async def lifespan(app):
        app.state.engine = Engine(directory)
        yield
        app.state.engine.close()

    app = FastAPI(
        title="Enterprise Agentic AI Copilot",
        version="2.0.0",
        lifespan=lifespan,
        description="Synthetic local CRM / ERP demonstration. All amounts in EUR cents.",
    )

    @app.exception_handler(KeyError)
    async def not_found(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(IntegrationUnavailable)
    async def integration_unavailable(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"detail": str(exc), "mock_substitution": False})

    @app.get("/health")
    def health():
        local_status = app.state.engine.provider.ollama_status()
        llm_label = (
            (
                "local Ollama ready; inference recorded per run"
                if local_status["status"] == "ready"
                else "Ollama unavailable; explicit offline fallback"
            )
            if app.state.engine.provider.is_ollama
            else (
                "provider configured (per-run execution recorded)"
                if app.state.engine.provider.configured
                else OFFLINE_LABEL
            )
        )
        return {
            "status": "ok",
            "synthetic": app.state.engine.integrations.fully_mock,
            "as_of": AS_OF,
            "crm": "local mock"
            if app.state.engine.integrations.crm_mode == "mock"
            else "real selected; see integrations status",
            "erp": "local mock"
            if app.state.engine.integrations.erp_mode == "mock"
            else "real selected; see integrations status",
            "llm": llm_label,
            "provider": app.state.engine.provider.kind,
            "model": app.state.engine.provider.model,
            "provider_validation": "See per-run provider_calls; configuration alone is not validation",
            "semantic_enabled": __import__("os").getenv("SEMANTIC_ENABLED", "0") == "1",
            "indexed_chunks": len(app.state.engine.index.chunks),
            "ollama": local_status,
            "integrations": app.state.engine.integrations.statuses(),
        }

    @app.get("/customers")
    def customers(search: str = Param(default="", max_length=100)):
        return app.state.engine.integrations.customers(search)

    @app.get("/customers/{customer_id}")
    def customer(customer_id: str):
        from copilot.models import CustomerLookup
        from pydantic import ValidationError

        try:
            lookup = CustomerLookup(customer_id=customer_id)
        except ValidationError as exc:
            raise HTTPException(422, "Expected a customer ID like C001") from exc
        return {
            "crm": app.state.engine.integrations.customer(lookup.customer_id),
            "erp": app.state.engine.integrations.invoices(lookup.customer_id),
            "contracts": app.state.engine.integrations.contracts(customer_id),
        }

    @app.post("/runs")
    def run(query: Query):
        return app.state.engine.run(query)

    @app.get("/runs")
    def runs():
        rows = app.state.engine.store.list_table("runs")[::-1]
        return [r for r in rows if r["status"] == "awaiting_approval"] + [
            r for r in rows if r["status"] != "awaiting_approval"
        ][:50]

    @app.get("/runs/{run_id}")
    def run_state(run_id: str):
        with app.state.engine.lock:
            return app.state.engine.snapshot(run_id)

    @app.post("/runs/{run_id}/decision")
    def decide(run_id: str, decision: Decision, x_approval_token: str | None = Header(default=None)):
        if not x_approval_token or not secrets.compare_digest(x_approval_token, approval_token()):
            with app.state.engine.store.connect() as db:
                app.state.engine.store.audit(db, "unauthorized_decision_rejected", {"run_id": run_id})
            raise HTTPException(403, "An authorized human approval token is required")
        try:
            return app.state.engine.decide(run_id, decision)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/search")
    def search(request: Search):
        app.state.engine.integrations.require_demo_documents()
        if request.customer_id:
            app.state.engine.store.customer(request.customer_id)
        return app.state.engine.index.search(request)

    @app.get("/contracts/{customer_id}/pdf")
    def contract_pdf(customer_id: str):
        app.state.engine.integrations.require_demo_documents()
        app.state.engine.store.customer(customer_id)
        path = directory / "contracts" / f"contract-{customer_id}.pdf"
        if not path.is_file():
            raise HTTPException(404, "Document unavailable")
        return FileResponse(path, media_type="application/pdf", filename=path.name)

    @app.get("/integrations")
    def integrations():
        return app.state.engine.integrations.statuses()

    @app.post("/integrations/{name}/probe")
    def probe(name: str, x_approval_token: str | None = Header(default=None)):
        if not x_approval_token or not secrets.compare_digest(x_approval_token, approval_token()):
            raise HTTPException(403, "Operator token required for an explicit external read probe")
        return app.state.engine.integrations.probe(name)

    @app.get("/proposals")
    def proposals():
        return app.state.engine.store.list_table("proposals")

    @app.get("/tasks")
    def tasks():
        return app.state.engine.store.list_table("tasks")

    @app.get("/audit")
    def audit():
        return app.state.engine.store.list_table("audit")

    @app.get("/evaluation")
    def evaluation():
        path = ROOT / "reports" / "evaluation.json"
        return (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"status": "not yet executed"}
        )

    @app.get("/evaluation/phase2")
    def phase2_evaluation():
        path = ROOT / "reports" / "phase2-evaluation.json"
        return (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"status": "not yet executed"}
        )

    return app


app = create_app()
