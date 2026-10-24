# GitHub publication preparation

**Description:** Evidence-grounded CRM/ERP renewal copilot with offline demo, optional bounded LangGraph LLM tools, hybrid local RAG and durable human approval.

**Topics:** `agentic-ai`, `langgraph`, `rag`, `crm`, `erp`, `fastapi`, `streamlit`, `human-in-the-loop`, `ai-engineering`.

Review the [audit](FINAL_PORTFOLIO_AUDIT.md), [validation](../reports/public/validation.json) and [publication scan](../reports/public/publication-check.json). Originally no Git metadata existed; a local repository was initialized for review. No commit, remote, push or publication is performed automatically.

Ignore rules exclude `.env`, environments, caches/weights/installers, runtime databases/indexes, logs and raw machine-specific reports. Small synthetic PDFs and reviewed evidence summaries remain publishable. Original evidence stays locally intact and is identified by hashes in the historical summary.

Inspect `git status --short` and candidates before committing. Keep MIT licensing and attribution. The second inspiration archive declared MIT but lacked a standalone license; no source modules were copied. Do not claim live enterprise integration or production readiness.

```powershell
.\.venv\Scripts\python.exe scripts/verify_offline.py --publication-only
```

This rechecks relative links, common secret/path signatures, file sizes and ignores without repeating tests. External URLs are not contacted; complete secret detection is not guaranteed.
