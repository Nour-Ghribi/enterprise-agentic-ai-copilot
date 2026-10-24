# Architecture and execution contracts

The [README diagram](../README.md#architecture) shows two paths through one LangGraph application. Offline is default; explicit provider configuration enables a bounded supervisor. Domain components are typed tools, not independent LLM agents.

| Module | Responsibility |
|---|---|
| `workflow.py` | StateGraph, deterministic nodes, interrupt/resume and scoped snapshots |
| `agent.py` | Observe-decide-act, context compaction and at most three corrections |
| `provider.py` | Optional native Ollama and compatible/Azure adapters; truthful per-call labels |
| `integrations.py` | Mock/real selection, prepared reads, verification status |
| `rag.py`, `semantic.py` | PDF provenance, lexical/cache-only learned retrieval, RRF |
| `grounding.py`, `risk.py`, `policy.py` | Exact correspondence, scoring, contradictions and action policy |
| `actions.py`, `store.py` | Run-bound proposals, transactions/idempotency and audit |
| `api.py`, `dashboard.py` | Validated API, approval authorization and Streamlit |

## Offline

`LLM_MODE=offline` disables generative calls and the legacy optional routing helper. No runtime discovery is needed. Deterministic routing selects CRM, ERP, document or risk nodes. Requested customer IDs remain scoped. `baseline` also forces this path when a provider is configured.

## Optional agentic execution

The model selects reads, observes results and chooses another read or final draft. Unknown tools, invalid arguments, foreign customers and unsupported claims are rejected. The example config permits 12 model turns, 40 reads and a 600-second local cooperative deadline. Remote caps are stricter. Limits are not an OS sandbox.

Repeated fact catalogues are compacted for generation; full observations stay persisted. Collected evidence survives a later tool error. Contract tools require a customer ID. Empty retrieval is missing evidence and can trigger reformulation.

Pydantic validates drafts. Bounded feedback requests missing evidence or corrected JSON. Native Ollama can use constrained JSON-schema correction once evidence is sufficient. Required keys/nonempty claims do not replace strict factual validation. The model still selects facts/actions. Exhaustion, provider errors or contradictory evidence cause safe abstention and withhold actions.

## Persistence and authority

`SqliteSaver` checkpoints the thread. `interrupt()` precedes execution; authorized `Command(resume=...)` continues it. Proposals are run-bound and fingerprints prevent duplicate committed tasks. The model has no write/approval tool. External adapters are read-only and disabled by default.

[Historical individual model runs](../reports/public/historical-ollama-evidence.json) and [current offline results](../reports/public/validation.json) are distinct evidence sets. Current tool/correction tests use controlled transports.
