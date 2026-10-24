# Remaining limitations

- Synthetic, loopback-bound prototype. Scores and offline recommendations are rules, not learned churn probabilities or autonomous reasoning.
- One optional supervisor uses Python tools. Independent specialist LLMs, multi-turn memory, parallel workers and learned planning memory are absent.
- Current validation is offline/simulated. Historical model passes do not validate this revision, live bilingual negations or real-provider Streamlit. No real inference is requested here.
- Exact canonical selection is restrictive. Source provenance does not establish arbitrary entailment or truth of source assertions.
- Negation/contradiction policies cover limited patterns. OCR, arbitrary amendments, multilingual legal interpretation, neural reranking and general injection guarantees are absent.
- Semantic retrieval needs optional packages and an existing MiniLM cache. Missing resources yield explicit lexical fallback. Weights are excluded from Git; startup/verification does not download them.
- The 12-question development evaluation is small, templated, filtered and not held out.
- Salesforce/Dynamics/SAP/Foundry reads are prepared, not live deployments. Full normalization, real contracts, OAuth refresh, remote writes and tenant validation are unfinished.
- Demo approval tokens are not enterprise identity. No SSO/RBAC, production tenancy, immutable audit, distributed coordination or formal security audit is claimed. Read endpoints are unauthenticated; use loopback.
- Approval is batch-based: no per-action editing, expiry or execution-time freshness revalidation. Fingerprints prevent duplicate committed tasks.
- Model limits are cooperative. Thirty-account LLM investigations exceed the default read budget; the LLM demo scopes C001 while baseline covers the portfolio.
- UI validation uses AppTest and real local HTTP, not a complete browser/accessibility matrix. Docker/Compose was not executed here.
- Publication scanning covers common secret/path signatures, sizes, ignores and relative links. It is not exhaustive and does not contact external URLs.

See the [final audit](FINAL_PORTFOLIO_AUDIT.md) for actual results.
