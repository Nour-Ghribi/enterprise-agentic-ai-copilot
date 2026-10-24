# Evaluation methodology

[Validation results](../reports/public/validation.json) and the [final audit](FINAL_PORTFOLIO_AUDIT.md) contain current commands, counts and exit codes. Older phase reports do not establish current results.

## Offline validation

`scripts/verify_offline.py` forces offline/mock modes and cache-only Hugging Face operation. It runs Ruff, dependency checks, full Pytest collection, workflow/API evaluation, retrieval evaluation, three-process approval and Streamlit AppTest with an isolated real FastAPI server.

Pytest skips live tests before discovery. Unmocked HTTP transports fail ordinary tests. Protocol fixtures remain `simulated_provider`; they are not inference benchmarks. Cases cover schema repair/exhaustion, scope, negations, references, missing/contradictory evidence, exact finance, PDF citations, authorization, rejection, restart and duplicate actions.

## Retrieval and business ground truth

`copilot.evaluate_phase2` compares lexical and hybrid search on 12 development questions with known customer/page targets. Metrics include Recall@1/3, MRR and citation provenance. MiniLM/FAISS is used only from existing resources. Missing semantic support is reported, not simulated.

The corpus is synthetic, templated and customer-filtered, with two pages per contract. Similarity thresholds were development-tuned. Results are not held-out production accuracy or evidence of generalization.

`copilot.evaluate` separately checks deterministic routing, finance/risk scores, source integrity, PDF matching, approval/idempotency and recovery. Keyword-routing success is not autonomous reasoning quality.

## Optional provider comparison

A = deterministic; B = LLM plus lexical; C = LLM plus hybrid. Standard evaluation runs A and leaves B/C unexecuted with null metrics. Non-live evaluation never probes Ollama, even with optional configuration. No real provider is evaluated in this finalization.

[Historical Ollama evidence](../reports/public/historical-ollama-evidence.json) records individual passes across revisions, with source hashes and timestamps. There is no single green live suite, independent entailment benchmark, general hallucination rate or production churn calibration.
