import sqlite3
import threading
import time
import uuid
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from copilot.actions import apply_decision, propose
from copilot.config import AS_OF
from copilot.llm import LanguageModel
from copilot.models import CustomerLookup, Decision, Query, Search
from copilot.rag import ContractIndex
from copilot.risk import analyze
from copilot.seed import seed
from copilot.store import Store
from copilot.tools import crm_lookup, erp_lookup
from copilot.agent import AgentWorkflow
from copilot.provider import ChatProvider
from copilot.policy import action_policy, selected_customers
from copilot.grounding import contradictions
from copilot.integrations import IntegrationHub, IntegrationUnavailable


class State(TypedDict, total=False):
    run_id: str
    request: dict
    intent: str
    customer_ids: list[str]
    route: dict
    crm: dict
    erp: dict
    documents: dict
    results: list[dict]
    proposals: list[dict]
    outcomes: list[dict]
    trace: list[dict]
    warnings: list[str]
    answer: str
    decision: dict
    messages: list[dict]
    agent_active: bool
    execution: dict
    action_policy: dict
    scope_explicit: bool
    llm_messages: list[dict]
    tool_calls: list[dict]
    provider_calls: list[dict]
    pending_calls: list[dict]
    iterations: int
    agent_deadline: float
    agent_stop: bool
    agent_retry: bool
    draft_repairs: int
    format_final: bool
    draft: dict | None
    facts: dict
    registers: dict
    contradictions: list[dict]
    grounded_answer: dict | None


class Engine(AgentWorkflow):
    def __init__(self, directory):
        self.store = Store(directory)
        seed(self.store)
        self.index = ContractIndex(directory)
        self.llm = LanguageModel()
        self.provider = ChatProvider()
        self.integrations = IntegrationHub(self.store)
        self.lock = threading.RLock()
        self.checkpoint_connection = sqlite3.connect(
            directory / "checkpoints.sqlite", check_same_thread=False
        )
        self.saver = SqliteSaver(self.checkpoint_connection)
        builder = StateGraph(State)
        for name in (
            "supervisor",
            "crm",
            "erp",
            "documents",
            "risk",
            "action",
            "approval",
            "execute",
            "answer",
        ):
            builder.add_node(name, getattr(self, name))
        for name in ("agent_decide", "agent_tools", "agent_finish"):
            builder.add_node(name, getattr(self, name))
        builder.add_edge(START, "supervisor")
        builder.add_conditional_edges(
            "supervisor",
            lambda s: (
                "agent_decide"
                if s.get("agent_active")
                else {"risk": "crm", "crm": "crm", "erp": "erp", "contracts": "documents", "help": "answer"}[
                    s["intent"]
                ]
            ),
        )
        builder.add_conditional_edges(
            "agent_decide",
            lambda s: "agent_decide" if s.get("agent_retry") and not s.get("agent_stop") else (
                "agent_tools" if s.get("pending_calls") and not s.get("agent_stop") else "agent_finish"
            ),
        )
        builder.add_edge("agent_tools", "agent_decide")
        builder.add_edge("agent_finish", "action")
        builder.add_conditional_edges("crm", lambda s: "erp" if s["intent"] == "risk" else "answer")
        builder.add_conditional_edges("erp", lambda s: "documents" if s["intent"] == "risk" else "answer")
        builder.add_conditional_edges("documents", lambda s: "risk" if s["intent"] == "risk" else "answer")
        builder.add_edge("risk", "action")
        builder.add_conditional_edges("action", lambda s: "approval" if s.get("proposals") else "answer")
        builder.add_edge("approval", "execute")
        builder.add_edge("execute", "answer")
        builder.add_edge("answer", END)
        self.graph = builder.compile(checkpointer=self.saver)

    @staticmethod
    def step(state, name, started, detail, **updates):
        return {
            **updates,
            "trace": state.get("trace", [])
            + [
                {
                    "agent": name,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "detail": detail,
                }
            ],
        }

    def supervisor(self, state):
        start = time.perf_counter()
        request = Query.model_validate(state["request"])
        customers = self.integrations.customers()
        requested_ids = selected_customers(request.message, customers, request.customer_id)
        local_status = (
            self.provider.ollama_status()
            if self.provider.is_ollama and request.execution_mode != "baseline"
            else None
        )
        if (
            request.execution_mode != "baseline"
            and self.provider.configured
            and (local_status is None or local_status["status"] == "ready")
        ):
            return self.step(
                state,
                "supervisor",
                start,
                "Started bounded LLM tool-selection loop",
                **self.begin_agent(state, request, customers),
            )
        router = self.llm
        if request.execution_mode == "baseline":
            router = LanguageModel()
            router.enabled = False
        route, mode, warnings = router.route(request.message, customers, request.customer_id)
        if local_status is not None:
            warnings.append(
                f"Ollama unavailable ({local_status['status']}); explicit offline fallback, no local inference claimed."
            )
        if request.execution_mode in {"agent", "hybrid"} and local_status is None:
            warnings.append("No configured provider; offline fallback. Real-provider validation pending.")
        if route.customer_id:
            if route.customer_id not in {c["id"] for c in customers}:
                raise KeyError("Unknown customer")
        ids = requested_ids or ([route.customer_id] if route.customer_id else [c["id"] for c in customers])
        return self.step(
            state,
            "supervisor",
            start,
            f"{mode}: {route.intent}; {route.reason}",
            intent=route.intent,
            route={**route.model_dump(), "mode": mode},
            customer_ids=ids,
            warnings=warnings,
            agent_active=False,
            execution={
                "mode": "offline",
                "requested": request.execution_mode,
                "provider": self.provider.kind,
                "fallback_reason": "baseline_requested"
                if request.execution_mode == "baseline"
                else local_status["status"]
                if local_status
                else "no_configured_provider",
            },
            action_policy=action_policy(request.message, request.prepare_actions),
        )

    def crm(self, state):
        start = time.perf_counter()
        records, warnings = {}, list(state.get("warnings", []))
        for cid in state["customer_ids"]:
            try:
                records[cid] = (
                    crm_lookup(self.store, CustomerLookup(customer_id=cid))
                    if self.integrations.crm_mode == "mock"
                    else {**self.integrations.customer(cid), "tickets": self.integrations.tickets(cid)}
                )
            except (OSError, sqlite3.Error, ValueError, IntegrationUnavailable) as exc:
                warnings.append(f"CRM unavailable for {cid}: {type(exc).__name__}")
        return self.step(
            state, "crm", start,
            f"Retrieved {len(records)} CRM accounts (mode={self.integrations.crm_mode})",
            crm=records, warnings=warnings
        )

    def erp(self, state):
        start = time.perf_counter()
        records, warnings = {}, list(state.get("warnings", []))
        for cid in state["customer_ids"]:
            try:
                records[cid] = (
                    erp_lookup(self.store, CustomerLookup(customer_id=cid))
                    if self.integrations.erp_mode == "mock"
                    else self.integrations.invoices(cid)
                )
            except (OSError, sqlite3.Error, ValueError, IntegrationUnavailable) as exc:
                warnings.append(f"ERP unavailable for {cid}: {type(exc).__name__}")
        return self.step(
            state,
            "erp",
            start,
            f"Retrieved {len(records)} ERP accounts (mode={self.integrations.erp_mode}); integer-cent arithmetic",
            erp=records,
            warnings=warnings,
        )

    def documents(self, state):
        start = time.perf_counter()
        records, warnings = {}, list(state.get("warnings", []))
        for cid in state["customer_ids"]:
            query = (
                "renewal expiration notice dispute service credits"
                if state["intent"] == "risk"
                else state["request"]["message"]
            )
            try:
                self.integrations.require_demo_documents()
                records[cid] = self.index.search(
                    Search(
                        query=query[:500],
                        customer_id=cid,
                        limit=4,
                        retrieval_mode="hybrid"
                        if state["request"].get("execution_mode") == "hybrid"
                        else "lexical",
                    )
                )
            except (OSError, ValueError, RuntimeError) as exc:
                warnings.append(f"Contract retrieval unavailable for {cid}: {type(exc).__name__}")
                records[cid] = []
        return self.step(
            state,
            "documents",
            start,
            "Contract retrieval with customer filtering; modes="
            + ",".join(sorted({p["retrieval_mode"] for passages in records.values() for p in passages})),
            documents=records,
            warnings=warnings,
        )

    def risk(self, state):
        start = time.perf_counter()
        results = []
        for cid in state["customer_ids"]:
            contracts = self.integrations.contracts(cid)
            result = analyze(
                self.integrations.customer(cid)["customer"],
                state.get("crm", {}).get(cid),
                state.get("erp", {}).get(cid),
                contracts[0] if contracts else None,
                state.get("documents", {}).get(cid, []),
            )
            conflicts = contradictions(contracts, state.get("documents", {}).get(cid, []))
            result["contradictions"] = conflicts
            if conflicts:
                result["warnings"].append(
                    "PDF and registry contradict each other; verify sources. Score uses registry."
                )
                result["score_is_lower_bound"] = True
            results.append(result)
        results.sort(key=lambda r: r["score"], reverse=True)
        if state["request"].get("execution_mode") != "baseline":
            for result in results[:3]:
                self.llm.explain(result)
        return self.step(
            state,
            "risk",
            start,
            "Applied documented five-signal rule; scores independent of model output",
            results=results,
        )

    def action(self, state):
        start = time.perf_counter()
        # Proposal intent may come from text; authorization NEVER comes from text or model output.
        request = state["request"]
        requested = action_policy(request["message"], request["prepare_actions"])["allow_proposals"]
        requested = requested and self.integrations.fully_mock  # Prepared enterprise adapters are read-only.
        results = state.get("results", [])
        if state.get("agent_active"):
            grounded = state.get("grounded_answer") or {}
            requested = (
                requested
                and not grounded.get("abstained", True)
                and not grounded.get("rejected")
                and not state.get("warnings")
            )
            recommendations = grounded.get("recommendations", [])
            results = [
                {
                    **r,
                    "suggested_actions": [
                        a["text"] for a in recommendations if a["customer_id"] == r["customer_id"]
                    ],
                }
                for r in results
                if any(a["customer_id"] == r["customer_id"] for a in recommendations)
            ]
        actions = propose(self.store, state["run_id"], results) if requested else []
        answer = f"Analyzed {len(state['results'])} customers; {len(actions)} follow-up proposals await explicit human approval."
        return self.step(
            state,
            "action",
            start,
            f"Prepared {len(actions)} proposals; no CRM task created",
            proposals=actions,
            answer=state.get("answer", answer) if state.get("agent_active") else answer,
        )

    def approval(self, state):
        value = interrupt(
            {
                "run_id": state["run_id"],
                "proposal_ids": [p["id"] for p in state["proposals"]],
                "message": "Human approval required before creating these mock CRM tasks.",
            }
        )
        decision = Decision.model_validate(value)
        return {"decision": decision.model_dump()}

    def execute(self, state):
        start = time.perf_counter()
        decision = Decision.model_validate(state["decision"])
        outcomes = apply_decision(
            self.store, state["run_id"], [p["id"] for p in state["proposals"]], decision
        )
        return self.step(
            state,
            "execute",
            start,
            "Persisted human decision, mock CRM tasks, and audit atomically",
            outcomes=outcomes,
        )

    def answer(self, state):
        start = time.perf_counter()
        intent = state["intent"]
        if state.get("agent_active"):
            text = state.get("answer") or "No verified answer available."
            return self.step(
                state,
                "answer",
                start,
                "Returned verified claims and separately labeled AI recommendations",
                answer=text,
                messages=[
                    {"role": "user", "content": state["request"]["message"]},
                    {"role": "assistant", "content": text},
                ],
            )
        if intent == "risk":
            text = f"Analyzed {len(state['results'])} customers using the {AS_OF} synthetic snapshot."
            if state.get("outcomes"):
                text += f" Human decision recorded for {len(state['outcomes'])} proposed actions."
        elif intent == "crm":
            text = f"Retrieved {len(state.get('crm', {}))} customer profiles, contacts, opportunities, tickets and interactions."
        elif intent == "erp":
            text = f"Retrieved {len(state.get('erp', {}))} invoice and order histories; amounts calculated in EUR cents."
        elif intent == "contracts":
            count = sum(len(v) for v in state.get("documents", {}).values())
            text = (
                f"Found {count} relevant contract passages with document and page references."
                if count
                else "No supporting contract passage found."
            )
        else:
            text = "Ask about renewal risk, customer contacts or tickets, invoices or orders, or contract clauses. Specify C001 or a customer name to narrow the search."
        messages = state.get("messages", []) + [
            {"role": "user", "content": state["request"]["message"]},
            {"role": "assistant", "content": text},
        ]
        return self.step(
            state, "answer", start, "Returned evidence and visible provenance", answer=text, messages=messages
        )

    def snapshot(self, run_id):
        config = {"configurable": {"thread_id": run_id}}
        snapshot = self.graph.get_state(config)
        if not snapshot.values:
            raise KeyError("Run not found")
        result = {**snapshot.values, "status": "awaiting_approval" if snapshot.next else "completed"}
        result["proposals"] = [p for p in self.store.list_table("proposals") if p["run_id"] == run_id]
        self.store.save_run(run_id, result)
        return result

    def run(self, query: Query):
        with self.lock:
            run_id = str(uuid.uuid4())
            start = time.perf_counter()
            self.graph.invoke(
                {
                    "run_id": run_id,
                    "request": query.model_dump(),
                    "trace": [],
                    "warnings": [],
                    "messages": [],
                },
                {"configurable": {"thread_id": run_id}, "recursion_limit": 60},
            )
            result = self.snapshot(run_id)
            result["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
            self.store.save_run(run_id, result)
            return result

    def decide(self, run_id: str, decision: Decision):
        with self.lock:
            current = self.snapshot(run_id)
            if current["status"] != "awaiting_approval":
                raise ValueError("Workflow is not waiting for a decision")
            self.graph.invoke(Command(resume=decision.model_dump()), {"configurable": {"thread_id": run_id}})
            return self.snapshot(run_id)

    def close(self):
        self.checkpoint_connection.close()
