# Current verification

```powershell
.\.venv\Scripts\python.exe scripts/verify_offline.py
```

No generative inference, Ollama startup or download is part of this command. [Actual results](../reports/public/validation.json) include counts, command exits, retrieval, approval restart and UI outcomes. [Publication checks](../reports/public/publication-check.json) review local candidates without pushing anything.

Live tests skip before discovery unless deliberately enabled. Simulated protocol/agentic tests remain executable. Cached CPU MiniLM inference is separate from generative inference.

See [FINAL_PORTFOLIO_AUDIT.md](FINAL_PORTFOLIO_AUDIT.md). Earlier raw reports/timestamps remain locally preserved in ignored archives. Their [public historical summary](../reports/public/historical-ollama-evidence.json) does not replace current verification.
