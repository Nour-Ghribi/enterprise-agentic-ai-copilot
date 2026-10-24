# Phase 2 implementation report

> Historical checkpoint for an earlier revision. Current offline-first scope and results are in [FINAL_PORTFOLIO_AUDIT.md](FINAL_PORTFOLIO_AUDIT.md). Later individual real-model passes are documented separately; the pending-validation statements below describe this earlier stage.

The existing application was evolved incrementally. The original archives and original phase-1 portable ZIP were preserved. Original test file hashes match that ZIP (reports/phase1-test-preservation.json).

| Area | Phase 1 | Phase 2 |
|---|---|---|
| Supervisor | Keyword/optional intent classification into fixed paths | Bounded provider decision/tool/observation loop with five typed read tools; offline baseline retained |
| Customers | First recognized ID | Multiple explicit IDs/names and enforced tool scope |
| Negation | Action keyword could prepare a draft despite prohibition | Conservative policy gives prohibition precedence, including over prepare_actions=True |
| Retrieval | Hash vectors + lexical FAISS | Same baseline plus real learned 384D MiniLM/ONNX embeddings and RRF hybrid |
| Documentary generation | Display of passages only | Actual passages reach model tool context; final selected facts carry PDF/page/hash |
| Claims | Existing reference IDs only | Exact canonical claim/customer correspondence, rejection of invented facts |
| Actions | Rules | Rules retained for baseline; provider selects applicable playbook action, priority and grounded context |
| Contradictions | Not detected | Recognized expiry/notice/dispute conflicts trigger warnings/abstention |
| Human approval | Durable LangGraph approval | Preserved with explicit read-only LLM boundary |
| Model telemetry | Limited / no verified calls | Per-call provider/model/response ID/usage/latency, actual tool arguments/results and simulation labels |
| Tests | 26 | 57 cases: original 26 unchanged plus 31 new |

## What has actually executed

- All 57 Pytest cases passed in the recorded suite run; semantic embeddings ran locally.
- The 12-query retrieval development evaluation returned lexical Recall@1/MRR 0.75 and hybrid 1.00.
- The real local API accepted the main two-customer request in offline hybrid fallback, returned scores 85/40, actual hybrid citations and no proposal/task.
- Baseline Streamlit approval and no-write comparison were exercised through a real isolated HTTP server.
- Structured model tool calling, grounding and recovery were exercised with explicit HTTP mocks. They are not real model benchmarks.
- Real-provider validation reports pending_credentials; no model quality scores are claimed for B/C.

## Scope of the agentic claim

The application now has a real implementation of an LLM-driven tool-use loop. Its execution with a real generative provider remains pending. It must be described as a tool-using supervisor architecture with tested local contracts, not as independently autonomous CRM/ERP agents or a scientifically validated production system.

See ARCHITECTURE.md, EVALUATION.md, VERIFICATION.md and LIMITATIONS.md for interfaces, exact checks and remaining boundaries.
