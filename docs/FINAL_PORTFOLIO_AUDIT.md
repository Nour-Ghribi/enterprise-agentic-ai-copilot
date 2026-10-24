# Final portfolio audit — 2026-10-24

The offline portfolio prototype passes the current verification. Its optional LLM orchestration is exercised through controlled transports; real-provider reliability on this revision remains unverified. Offline routing, scoring and recommendations are deterministic Python logic, not autonomous reasoning. CRM, ERP and document tools are Python services called by one optional LLM supervisor, not separate autonomous LLM agents.

No Ollama process was started or queried, generative model loaded, model downloaded, heavy runtime installed, commercial API called or external credentials modified during this finalization. Existing global Ollama installation/model files were left untouched. Cached MiniLM embedding inference is local retrieval, not generative LLM inference.

## Implemented and verified now

| Component | Source / functions | Current execution evidence |
|---|---|---|
| Explicit offline default | `copilot/config.py:OFFLINE_LABEL`, `copilot/api.py`, `.env.example`, `dashboard.py` | API and UI expose **Offline deterministic demo — no generative LLM inference.** Optional Ollama status is `not_selected`, inference false. Offline comparison test forbids `ChatProvider.complete`. |
| Synthetic CRM/ERP and business rules | `copilot/workflow.py:Engine.crm`, `erp`, `risk`, `action`; local store and scoring modules | API/workflow suite and evaluator pass. C001/C004 comparison scores 85/40; no tasks when prohibited. Five golden risk cases pass, including incomplete C005. Financial arithmetic remains deterministic in integer EUR cents. |
| Typed tool selection and bounded LangGraph loop | `copilot/agent.py:AgentWorkflow.agent_decide`, `agent_tools`, `agent_finish`; `copilot/provider.py:ChatProvider` | Controlled HTTP transports exercise actual graph/provider serialization, multiple read tools, malformed arguments/answers, scope, safe abstention and evidence validation. These are simulated model decisions, not real inference. |
| Output recovery and compaction | `generation_messages`, `retry_draft`, `final_generation_messages`; `tests/test_context_budget.py`, `tests/test_portfolio_recovery.py` | Latest good evidence survives a subsequent tool error; stored raw observations remain intact. Native Ollama-format fixture verifies required JSON schema and absence of tools in the correction request. Three failed repairs terminate safely after five calls in the malformed-output fixture, with no write. |
| Negations and approval boundary | `Engine.action`, `approval`, `execute`, `decide`; recovery and policy tests | Explicit prohibitions override `prepare_actions=True`, including after a simulated structured correction. A permitted proposal pauses with zero tasks, then an explicit human decision on a fresh Engine creates one mock task. Broader English/French policy tests are offline/fixture tests. |
| Local hybrid RAG | `copilot/rag.py:ContractIndex.ingest`, `ensure_semantic`, `search`, `lexical_search`; `copilot/semantic.py:SemanticEncoder` | Cached MiniLM ONNX CPU produces 384-dimensional embeddings; lexical and semantic FAISS retrieval are fused. Actual 12-query hybrid results: Recall@1=1.00, Recall@3=1.00, MRR=1.00, provenance rate=1.00. Lexical results: 0.75/0.75/0.75, provenance=1.00. |
| PDF provenance and missing/conflicting evidence | RAG ingestion, grounding and policy modules; offline evaluations/tests | 30 synthetic two-page PDFs yield 60 chunks. Baseline PDF passage checks 60/60 and retrieval targets 6/6 pass. Citations bind document/page/chunk/hash, and canonical claims are validated against observations. Missing evidence and supported contract conflicts suppress unsupported actions. |
| Durable human approval | `Engine.approval` uses `interrupt()`; `decide` uses `Command(resume=...)`; SQLite `SqliteSaver` and local store | Three separate Python processes: paused/0 tasks → authorized approval/1 task → duplicate rejected/still 1 task/audit persisted. Suite also covers rejection, suppression, authorization, cross-run binding and idempotence. Writes are local mock CRM rows. |
| Streamlit and API | `dashboard.py`, `copilot/api.py`, `scripts/smoke_ui.py` | Six tabs render with zero AppTest exceptions. Main offline demo pauses; human form resumes graph and persists 12 mock tasks. Lookup, two-customer comparison/no extra task and an explicitly simulated provider UI path pass. |
| Actual startup | `launch.py` | Owned launcher started both loopback services; API health, API docs and Streamlit health returned HTTP 200. Health confirmed offline, 60 indexed chunks, all integrations mock. Only this owned process tree was stopped afterward. This checks HTTP readiness; interactive UI coverage comes from AppTest. |

Evidence: [full verification summary](../reports/public/validation.json), [launcher smoke](../reports/public/launch-smoke.json), [cached encoder manifest](../reports/public/semantic-model-manifest.json). Baseline routing checks are keyword-routing checks, not reasoning benchmarks. Learned retrieval scores concern this small synthetic development set, not a held-out generalization claim.

## Previously verified — historical Ollama only

Original reports from 2026-10-21 were inspected without contacting Ollama. They record Ollama **0.40.7**, **qwen3:1.7b**, digest `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`. Initial basic inference timestamp: **2026-10-21T20:50:57.208404+00:00**, latency **8979.01 ms**.

| Historical individual pass | Original artifact | Artifact write timestamp UTC | Provider calls / tool calls / verified claims |
|---|---|---|---|
| Customer contact | `ollama-e2e-third-attempt.json` | 2026-10-21 21:01:53.041182 | 2 / 1 / 2 |
| Invoices | same artifact | same timestamp | 2 / 1 / 1 |
| Human-approved workflow | same artifact | same timestamp | 4 / 4 / 6 |
| Contract clause with PDF/page/hash | `ollama-focused.json` | 2026-10-21 21:07:17.464734 | 6 / 3 / 4 |
| C001/C004 comparison, scores 85/40 | `ollama-comparison-correction.json` | 2026-10-21 21:14:04.606383 | 6 / 8 / 11 |

The comparison artifact contains a pass, resolving the uncertainty in the handover. These are individual successes across different runs/revisions, **not one successful full live suite**. Artifact write timestamps are not individual inference timestamps. All five successful records report zero structured corrections; they do not prove the recovered native schema-correction path worked with a live model.

[Portable historical evidence](../reports/public/historical-ollama-evidence.json) includes source SHA256, run IDs, counters and citations. Original raw artifacts and copies retain their file timestamps locally under ignored `reports/` and `reports/archive/2026-10-21/`; earlier documents/README are archived under ignored `docs/archive/2026-10-21/`. No current-revision real inference, complete green live suite, real bilingual-negation test or real-provider Streamlit run is claimed.

## Simulated

- All business records, contract PDFs, invoices, support incidents and local CRM tasks are synthetic. The business snapshot remains 2026-10-21; it is independent of this audit date.
- Provider `httpx.MockTransport` fixtures return controlled model messages/tool calls. They test orchestration, validation and safety, not model intelligence, prompt robustness or real latency.
- Enterprise API fixtures verify request/response contracts, field mappings and errors. They establish no live enterprise connection.
- Offline recommendations come from rules/playbooks. Optional LLM recommendations select eligible actions and observed fact IDs; action labels remain controlled templates.

## Prepared but unverified

Salesforce CRM, Microsoft Dynamics 365/Dataverse, SAP ERP/OData and Azure AI Foundry adapters/configuration remain available, default mock, external fields blank in `.env.example`. No tenant endpoint, credential or remote API was exercised. Configured-but-unverified and live-verified status are distinct; fixture traffic cannot mark live verification. External writes are unsupported.

Ollama, OpenAI-compatible and Azure OpenAI providers remain configurable for future explicit use. The current revision's real-provider output quality, correction behavior, negation reliability, end-to-end latency and UI behavior were intentionally not tested. Five original Ollama scenario cases plus two live-negation cases are skipped, not counted as successes.

## Actual test results

Environment: **Windows, Python 3.10.11**, existing `.venv`, cached semantic model/dependencies. No dependency/runtime installation was performed in this finalization. Full runner executed **2026-10-24 10:16:42–10:19:59 UTC**. It forces offline LLM/mock integrations and cache-only Hugging Face behavior. Ordinary Pytest fixtures reject unmocked HTTP transports; live-marked tests skip before provider discovery unless explicitly opted in.

Reproduce from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/verify_offline.py
```

| Executed command (using that interpreter) | Result | Runner duration |
|---|---|---|
| `python -m ruff check copilot tests scripts dashboard.py launch.py conftest.py` | Passed, exit 0 | 0.370 s |
| `python -m pip check` | No broken requirements, exit 0 | 4.358 s |
| `python -m pytest -q -rs --junitxml=reports/portfolio-pytest.xml` | **109 collected: 102 passed, 7 skipped, 0 failures, 0 errors** | 114.676 s |
| `python -m copilot.evaluate` | Passed, exit 0 | 15.807 s |
| `python -m copilot.evaluate_phase2` | Passed, cached lexical/hybrid retrieval and offline comparison | 10.373 s |
| `python scripts/check_persistent_approval.py` | Passed across 3 processes | 18.478 s |
| `python scripts/smoke_ui.py` | Passed; 6 tabs, 0 exceptions | 33.584 s |

Pytest's own summary reports 98.05 s; runner duration includes process startup/teardown. Skip reason: `Real LLM inference not executed: offline policy; --run-live-llm is opt-in.` Skips are four parametrized cases and one approval case in `tests/test_ollama.py`, and two cases in `tests/test_ollama_negations.py`. No live opt-in command was executed.

Baseline evaluator: routing 4/4, golden risk 5/5, retrieval targets 6/6, PDF passages 60/60, signal references 8/8, approval/idempotence 6/6, error handling 1/1 and end-to-end scenarios 6/6. Phase-2 deterministic comparison executes four cases; both real-LLM comparison arms execute zero and retain unavailable/null metrics rather than fabricated quality scores. Additional actual `python launch.py` readiness smoke passed at 10:23:39 UTC.

Raw JUnit and command logs are retained locally under ignored `reports/portfolio-pytest.xml` and `reports/offline-checks/`. Public results contain portable summaries without personal filesystem paths.

## Files changed and recovery scope

There was no existing `.git` directory to provide a prior tracked diff. A local Git repository was initialized for publication-candidate checks; nothing was staged, committed, assigned a remote or pushed. Prior implementation was inspected and retained rather than reset.

- Recovered planner/provider, schema repair, bounded retries, scoped contract search, compaction and timeout changes remain in place. Fixed demonstrated evidence loss in `copilot/agent.py:generation_messages` when a tool error followed a successful observation; added a regression test.
- Updated `copilot/config.py`, `copilot/api.py`, `copilot/workflow.py`, `copilot/evaluate_phase2.py`, `dashboard.py` and `.env.example` for honest offline labeling/defaults, actual retrieval-mode traces, no optional-provider discovery during offline evaluation and no external font fetch. Private `.env` mode alone was switched to offline.
- Added root `conftest.py`, `tests/test_portfolio_recovery.py`, the compaction regression in `tests/test_context_budget.py` and `scripts/verify_offline.py`. Existing tests were preserved, including opt-in live tests; none was removed to suppress failure.
- Updated `.gitignore`, `pyproject.toml`, README, setup/architecture/evaluation/verification/limitations/audit documentation and attribution links. Added screenshot/publication guidance and public evidence summaries. Earlier documents and raw reports were preserved in ignored archives.

## Remaining limitations

The offline planner is deterministic. Tool-loop tests cannot establish autonomous reasoning or future real-model reliability. Exact canonical claim matching/provenance does not establish general semantic entailment. Negation policies are conservative pattern rules; supported contradiction checks are domain-specific.

The 12-query retrieval set is small, customer-filtered and synthetic. Missing cached MiniLM resources cause explicit lexical fallback; model weights are not bundled for GitHub and no resource auto-download is required. Fresh dependency installation can require internet; application runtime does not require internet/API keys.

Production SSO/RBAC, production approval identity, distributed execution, remote write APIs, OAuth lifecycle, OCR, neural reranking and conversational memory are absent. The public local approval token is demonstration authentication only. Docker/Compose, browser screenshots/cross-browser behavior, external URLs and live tenant/provider behavior were not verified. AppTest and HTTP readiness are narrower than a browser-based deployment audit.

## Portfolio readiness and startup

Ready for GitHub publication **as an honestly labeled offline prototype with optional LLM code**, not as a production deployment or a fully live-validated autonomous multi-agent system. All current offline verification checks pass. Current real-provider verification is intentionally outside this finalization's scope.

[Publication check](../reports/public/publication-check.json) inspects publishable Git candidates for common secret signatures, personal Windows paths, oversized files, relative links and ignore rules. It excludes private `.env`, virtual environments, model weights/installers, runtime databases/logs/caches and raw machine reports. Required small synthetic PDFs and license notices remain publishable. This heuristic check is not an exhaustive secret/security audit; external links are not contacted. No GitHub push was performed. Suggested description/topics and publication review instructions are in [GitHub publication](GITHUB_PUBLICATION.md).

Exact startup in PowerShell, **from the repository root**:

```powershell
$env:LLM_MODE = 'offline'
.\.venv\Scripts\python.exe launch.py
```

Open `http://127.0.0.1:8501` and `http://127.0.0.1:8000/docs`. Default integration modes are mock. Ctrl+C stops owned application services. See [setup](LOCAL_SETUP.md) for a fresh Python environment and optional cache configuration. No Ollama runtime is required for this demonstration.
