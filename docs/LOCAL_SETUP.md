# Local setup: offline by default

The standard application/tests require no Ollama process, generative weights, API key or external connection. Finalization on 2026-10-24 performs no real LLM inference and does not alter the global Ollama installation/models.

```powershell
$env:LLM_MODE = 'offline'
.\.venv\Scripts\python.exe launch.py
```

Open http://127.0.0.1:8501 and http://127.0.0.1:8000/docs. The launcher checks ports and owns only the services it starts. Logs are ignored by Git. Initial Python dependency setup is in the [README](../README.md). Preserve private configuration; copy `.env.example` only if `.env` does not exist. Enterprise modes default to mock.

## Cache-only semantic retrieval

Set `SEMANTIC_ENABLED=1` to use the existing MiniLM cache. `SEMANTIC_CACHE_DIR` can point at another existing compatible cache; default is `data/models/`. FastEmbed uses `local_files_only=True`. Missing resources produce a semantic warning and lexical fallback. No model download occurs during startup/default verification; weights are excluded from Git.

The verification runner sets `HF_HUB_OFFLINE=1` and disables Hugging Face telemetry. CPU embedding inference is distinct from generative LLM inference.

## Optional providers: future deliberate use only

These settings are documentation, not commands executed in this finalization.

```dotenv
# Optional local provider; requires an independently configured server/model.
LLM_MODE=ollama
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:1.7b
OLLAMA_NUM_CTX=8192
OLLAMA_TIMEOUT_SECONDS=300
```

Existing bootstrap/real-model scripts remain optional. Neither `launch.py` nor standard verification calls them. A running Ollama server retains its own storage/settings. The application rejects remote/cloud-backed Ollama inference configuration.

```dotenv
# Optional compatible Chat Completions service.
LLM_MODE=openai
LLM_PROVIDER=openai
LLM_BASE_URL=https://YOUR-COMPATIBLE-SERVICE/v1
LLM_MODEL=YOUR-TOOL-CAPABLE-MODEL
LLM_API_KEY=YOUR-KEY
```

```dotenv
# Optional Azure OpenAI v1 resource and deployment.
LLM_MODE=azure
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=YOUR-DEPLOYMENT
AZURE_OPENAI_API_KEY=YOUR-KEY
```

External fields in `.env.example` are blank. Credentials/entitlements are not verified. Keep `LLM_MODE=offline` for normal use. Unavailable providers report explicit fallback/safe failure. Live tests also require `--run-live-llm`; that option was not used here.

[Historical model evidence](../reports/public/historical-ollama-evidence.json) is not current-revision provider validation. See the [final audit](FINAL_PORTFOLIO_AUDIT.md).
