"""Real local retrieval evaluation and optional live-provider A/B/C comparison.

Mock provider tests are deliberately not converted into LLM benchmark scores.
"""

import argparse
import json
import platform
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from copilot.config import ROOT
from copilot.models import Query, Search
from copilot.workflow import Engine

RETRIEVAL_CASES = [
    ("non-renewal notice", "C001", 1),
    ("expiration", "C002", 1),
    ("critical incidents response", "C003", 2),
    ("legal dispute", "C004", 2),
    ("urgent outage acknowledgement", "C003", 2),
    ("How quickly must a serious service failure receive a reply?", "C006", 2),
    ("When does the agreement end?", "C002", 1),
    ("advance warning before ending the agreement", "C010", 1),
    ("deadline to settle a bill", "C008", 2),
    ("compensation for service failures", "C004", 2),
    ("contractual dispute", "C004", 2),
    ("renewal termination", "C012", 1),
]

SCENARIOS = [
    {
        "message": "Who is the contact for C003?",
        "ids": ["C003"],
        "tools": ["get_customer"],
        "kind": "contact",
    },
    {"message": "Show invoices for C001", "ids": ["C001"], "tools": ["get_invoices"], "kind": "invoice"},
    {
        "message": "What is the non-renewal notice for C002?",
        "ids": ["C002"],
        "tools": ["search_contracts"],
        "kind": "contract",
    },
    {
        "message": "Compare customers C001 and C004, examine their invoices and contracts, identify renewal risks, and recommend follow-up actions without creating any CRM task.",
        "ids": ["C001", "C004"],
        "tools": ["get_customer", "get_invoices", "get_tickets", "search_contracts"],
        "kind": "risk",
    },
]


def retrieval_metrics(index, mode):
    rows, recall1, recall3, reciprocal, valid = [], [], [], [], []
    start = time.perf_counter()
    for question, cid, page in RETRIEVAL_CASES:
        hits = index.search(Search(query=question, customer_id=cid, retrieval_mode=mode, limit=3))
        rank = next((i for i, h in enumerate(hits, 1) if h["page"] == page and h["customer_id"] == cid), None)
        recall1.append(int(rank == 1))
        recall3.append(int(rank is not None))
        reciprocal.append(1 / rank if rank else 0)
        for hit in hits:
            chunk = next(c for c in index.chunks if c["id"] == hit["id"])
            valid.append(hit["text"] == chunk["text"] and hit["page"] == chunk["page"])
        rows.append(
            {
                "query": question,
                "customer_id": cid,
                "expected_page": page,
                "rank": rank,
                "returned_mode": hits[0].get("retrieval_mode") if hits else None,
            }
        )
    return {
        "n": len(rows),
        "recall_at_1": statistics.mean(recall1),
        "recall_at_3": statistics.mean(recall3),
        "mrr": statistics.mean(reciprocal),
        "citation_provenance_rate": statistics.mean(valid) if valid else None,
        "total_latency_ms": round((time.perf_counter() - start) * 1000, 2),
        "cases": rows,
    }


def evaluate(live=False):
    with tempfile.TemporaryDirectory(prefix="copilot-phase2-eval-") as temp:
        engine = Engine(Path(temp))
        comparison = {}
        for name, mode in [
            ("A_deterministic", "baseline"),
            ("B_LLM_lexical", "agent"),
            ("C_LLM_hybrid", "hybrid"),
        ]:
            local_unavailable = (
                live and engine.provider.is_ollama and engine.provider.ollama_status()["status"] != "ready"
            )
            if mode != "baseline" and (not live or not engine.provider.configured or local_unavailable):
                comparison[name] = {
                    "status": "pending_ollama_runtime" if local_unavailable else "pending_real_provider",
                    "n": 0,
                    "metrics": None,
                    "reason": "Requires --live and a ready local Ollama model; no API key required and no mock scores substituted"
                    if engine.provider.is_ollama
                    else "Requires --live and configured provider credentials; no mock scores substituted",
                }
                continue
            cases = []
            for scenario in SCENARIOS:
                result = engine.run(Query(message=scenario["message"], execution_mode=mode))
                if mode == "baseline":
                    mapping = {"crm": "get_customer", "erp": "get_invoices", "documents": "search_contracts"}
                    selected = {mapping[t["agent"]] for t in result["trace"] if t["agent"] in mapping}
                    claims = rejected = None
                else:
                    selected = {c["name"] for c in result["tool_calls"] if c["status"] == "ok"}
                    grounded = result.get("grounded_answer") or {}
                    claims = len(grounded.get("verified_claims", []))
                    rejected = sum(c["type"] == "claim" for c in grounded.get("rejected", []))
                if scenario["kind"] == "risk":
                    success = {r["customer_id"]: r["score"] for r in result.get("results", [])} == {
                        "C001": 85,
                        "C004": 40,
                    } and not result["proposals"]
                elif scenario["kind"] == "contract":
                    success = (
                        ("60 days" in result["answer"])
                        if mode != "baseline"
                        else bool(result.get("documents", {}).get("C002"))
                    )
                else:
                    success = (
                        bool(claims) if mode != "baseline" else bool(result.get("crm") or result.get("erp"))
                    )
                calls = result.get("provider_calls", [])
                cases.append(
                    {
                        "question": scenario["message"],
                        "mode": result.get("execution"),
                        "selected_tools": sorted(selected),
                        "tool_selection_exact": selected == set(scenario["tools"]),
                        "task_success": success,
                        "accepted_factual_claims": claims,
                        "rejected_factual_claims": rejected,
                        "latency_ms": result["latency_ms"],
                        "provider_calls": calls,
                        "input_tokens": sum(c.get("usage", {}).get("prompt_tokens", 0) for c in calls),
                        "output_tokens": sum(c.get("usage", {}).get("completion_tokens", 0) for c in calls),
                    }
                )
            comparison[name] = {
                "status": "executed",
                "n": len(cases),
                "tool_selection_accuracy": statistics.mean(c["tool_selection_exact"] for c in cases),
                "task_success_rate": statistics.mean(c["task_success"] for c in cases),
                "cases": cases,
            }
        lexical = retrieval_metrics(engine.index, "lexical")
        semantic_ready = engine.index.ensure_semantic()
        hybrid = (
            retrieval_metrics(engine.index, "hybrid")
            if semantic_ready
            else {"status": "unavailable", "reason": engine.index.semantic_error}
        )
        report = {
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "embedding_model": engine.index.encoder.name if semantic_ready else None,
                "embedding_runtime": "FastEmbed/ONNX CPU" if semantic_ready else None,
            },
            "real_provider_configured": engine.provider.configured,
            "live_requested": live,
            "comparison": comparison,
            "retrieval": {"lexical": lexical, "hybrid": hybrid},
            "claim_evaluation": {
                "policy": "Exact canonical fact correspondence; arbitrary factual paraphrases rejected",
                "real_llm_supported_claim_rate": None
                if not live or not engine.provider.configured
                else "See accepted/rejected counts in cases",
                "real_llm_hallucination_rate": None,
                "note": "No independent semantic entailment benchmark. Rejected claims are observable, not a complete hallucination estimate.",
            },
            "limitations": [
                "Small development set, 12 retrieval queries and 4 workflow scenarios; not a held-out benchmark.",
                "Customer-filtered corpus has two pages per customer; Recall@3 is an easy measure.",
                "Threshold 0.25 was adjusted on a development paraphrase; no generalization claim.",
                "A baseline tool mapping is only an approximation of the same task interface.",
                "Provider B/C metrics are null without actual provider execution.",
                "Citation provenance does not establish full natural-language entailment.",
            ],
        }
        engine.close()
    target = ROOT / "reports" / "phase2-evaluation.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "comparison": {k: {x: v[x] for x in ("status", "n")} for k, v in comparison.items()},
                "retrieval": {
                    k: {x: v[x] for x in ("n", "recall_at_1", "recall_at_3", "mrr") if x in v}
                    for k, v in report["retrieval"].items()
                },
                "report": str(target),
            },
            indent=2,
        )
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live", action="store_true", help="Execute configured provider; may incur API charges"
    )
    evaluate(live=parser.parse_args().live)
