"""Compute narrow, reproducible synthetic metrics, never illustrative invented scores."""

import json
import os
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfReader

from copilot.api import create_app
from copilot.config import ROOT
from copilot.models import Decision, Query, Search
from copilot.workflow import Engine


def metric(passed, total):
    return {"passed": passed, "total": total, "rate": round(passed / total, 4) if total else None}


def evaluate():
    os.environ["LLM_MODE"] = "offline"  # This command deliberately evaluates the local baseline only.
    latencies, cases = [], []
    with tempfile.TemporaryDirectory(prefix="copilot-eval-") as tmp:
        engine = Engine(Path(tmp) / "engine")
        engine.llm.enabled = False
        selection = []
        for question, expected in [
            ("Who is the contact for C003?", ["supervisor", "crm", "answer"]),
            ("Show invoices for C001", ["supervisor", "erp", "answer"]),
            ("What is the notice clause for C002?", ["supervisor", "documents", "answer"]),
            ("Tell me a joke", ["supervisor", "answer"]),
        ]:
            start = time.perf_counter()
            result = engine.run(Query(message=question))
            latencies.append((time.perf_counter() - start) * 1000)
            actual = [s["agent"] for s in result["trace"]]
            selection.append(actual == expected)
            cases.append(
                {
                    "case": question,
                    "expected_agents": expected,
                    "actual_agents": actual,
                    "passed": selection[-1],
                }
            )
        scores, grounding, retrieval = [], [], []
        all_ids = {r["id"] for kind in engine.store.collections for r in engine.store.records(kind)}
        for cid, expected_score, expected_level in [
            ("C001", 85, "High"),
            ("C002", 20, "Low"),
            ("C003", 0, "Low"),
            ("C004", 40, "Medium"),
            ("C005", 0, "Unknown"),
        ]:
            start = time.perf_counter()
            run = engine.run(Query(message="Analyze renewal risk", customer_id=cid))
            latencies.append((time.perf_counter() - start) * 1000)
            result = run["results"][0]
            scores.append(result["score"] == expected_score and result["risk_level"] == expected_level)
            for signal in result["signals"]:
                grounding.append(
                    all(ref in all_ids for ref in signal["evidence_ids"]) and bool(signal["evidence_ids"])
                )
            cases.append(
                {
                    "case": cid,
                    "expected_score": expected_score,
                    "actual_score": result["score"],
                    "expected_level": expected_level,
                    "actual_level": result["risk_level"],
                    "passed": scores[-1],
                }
            )
        for query, cid, page in [
            ("non-renewal notice", "C001", 1),
            ("expiration", "C002", 1),
            ("critical incidents response", "C003", 2),
            ("legal dispute", "C004", 2),
            ("invoices payable", "C006", 2),
            ("renewal termination", "C010", 1),
        ]:
            hits = engine.index.search(Search(query=query, customer_id=cid))
            success = bool(hits) and hits[0]["customer_id"] == cid and hits[0]["page"] == page
            retrieval.append(success)
            cases.append(
                {
                    "case": query,
                    "customer_id": cid,
                    "expected_page": page,
                    "actual_page": hits[0]["page"] if hits else None,
                    "passed": success,
                }
            )
        citation_checks = []
        for chunk in engine.index.chunks:
            page = PdfReader(engine.store.directory / "contracts" / chunk["document"]).pages[
                chunk["page"] - 1
            ]
            citation_checks.append(chunk["text"] in page.extract_text())
        approval_checks = []
        run = engine.run(Query(message="Analyze risk and prepare actions", customer_id="C001"))
        approval_checks.append(run["status"] == "awaiting_approval" and not engine.store.list_table("tasks"))
        fresh = Engine(engine.store.directory)
        resumed = fresh.decide(run["run_id"], Decision(approved=True, actor="Synthetic evaluation reviewer"))
        approval_checks.append(resumed["status"] == "completed" and len(fresh.store.list_table("tasks")) == 1)
        try:
            fresh.decide(run["run_id"], Decision(approved=True, actor="Synthetic evaluation reviewer"))
            approval_checks.append(False)
        except ValueError:
            approval_checks.append(len(fresh.store.list_table("tasks")) == 1)
        duplicate = fresh.run(Query(message="Analyze risk and prepare actions", customer_id="C001"))
        approval_checks.append(not duplicate["proposals"])
        fresh.close()
        rejected = engine.run(Query(message="Analyze risk and prepare actions", customer_id="C004"))
        engine.decide(rejected["run_id"], Decision(approved=False, actor="Synthetic evaluation reviewer"))
        approval_checks.append(len(engine.store.list_table("tasks")) == 1)
        with patch("copilot.workflow.erp_lookup", side_effect=OSError("Synthetic outage")):
            failed = engine.run(Query(message="Analyze risk and prepare actions", customer_id="C001"))
        error_recovery = (
            failed["status"] == "completed"
            and bool(failed["warnings"])
            and failed["results"][0]["score_is_lower_bound"]
            and not failed["proposals"]
        )
        completion = [all(selection), all(scores), all(retrieval), all(approval_checks), error_recovery]
        # Persist the exact demo evidence from an isolated synthetic database.
        demo = engine.run(
            Query(message="Which customers have highest renewal risk? Prepare suitable follow-up actions.")
        )
        completion.append(len(demo["results"]) == 30 and demo["status"] == "awaiting_approval")
        engine.close()
        with TestClient(create_app(Path(tmp) / "api")) as client:
            sample = client.post(
                "/runs", json={"message": "Analyze risk and prepare actions", "customer_id": "C001"}
            ).json()
            decision_url = f"/runs/{sample['run_id']}/decision"
            denied = client.post(decision_url, json={"approved": True, "actor": "Evaluation reviewer"})
            approval_checks.append(denied.status_code == 403 and not client.get("/tasks").json())
        output = {
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "offline synthetic evaluation",
            "tool_selection_exact_match": metric(sum(selection), len(selection)),
            "risk_score_and_level_correctness": metric(sum(scores), len(scores)),
            "retrieval_customer_page_hit_at_1": metric(sum(retrieval), len(retrieval)),
            "citation_exact_pdf_passage_match": metric(sum(citation_checks), len(citation_checks)),
            "signal_reference_integrity": metric(sum(grounding), len(grounding)),
            "approval_and_idempotence": metric(sum(approval_checks), len(approval_checks)),
            "error_recovery": metric(int(error_recovery), 1),
            "scenario_completion": metric(sum(completion), len(completion)),
            "latency_ms": {
                "samples": len(latencies),
                "median": round(statistics.median(latencies), 2),
                "max": round(max(latencies), 2),
                "cold_start_excluded": True,
            },
            "limitations": [
                "Small handcrafted synthetic test set; no production distribution or predictive validation.",
                "Lexical hashing vectors; this is not a semantic embedding benchmark.",
                "Grounding checks reference integrity and exact source excerpts, not semantic entailment.",
                "Live LLM quality and real Salesforce/SAP connections were not evaluated.",
            ],
            "cases": cases,
        }
        reports = ROOT / "reports"
        reports.mkdir(exist_ok=True)
        (reports / "evaluation.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
        (reports / "demo-run.json").write_text(json.dumps(demo, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in output.items() if k != "cases"}, indent=2))
        return output


if __name__ == "__main__":
    evaluate()
