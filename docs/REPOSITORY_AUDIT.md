# Supplied repository audit

The supplied ZIPs were extracted into the sibling `reference_sources/azure` and `reference_sources/salesforce_sap` directories. Entry destinations were checked to remain under the extraction root. The original Downloads archives were not modified. `reports/source-archives.json` records their SHA-256 hashes and sizes.

## Azure multi-agent LangGraph

Source: https://github.com/AzureCosmosDB/multi-agent-langgraph (21 archive entries). Inspected `multi_agent_service.py`, `azure_open_ai.py`, `azure_cosmos_db.py`, `ai_chat_bot.py`, requirements and license.

The source builds React-style specialized agents with transfer tools returning LangGraph Commands. It shares message state, tracks an active agent per user session, retrieves products using Cosmos vector search, and pauses through a human node. CosmosDBSaver checkpoints conversations. The Gradio UI streams graph updates and maintains session IDs.

Architectural ideas adapted: explicit specialist nodes, shared state, tool isolation, conditional delegation, durable checkpointing and human interrupts. The new implementation uses a bounded supervisor workflow, SQLite checkpoints and local customer-filtered FAISS retrieval. No Azure code or original prompt was copied.

Discarded: shopping/product/refund business logic, mandatory cloud credentials, import-time Cosmos provisioning, cloud vector stores, Gradio UI and global session variables. Source dependencies include LangGraph 0.2.74, LangChain 0.3.19, Azure Cosmos beta and Azure-specific checkpointing. They were not combined with the new dependency set.

License: the archive includes the MIT license, copyright Microsoft Corporation. An unchanged copy is retained in `licenses/Azure-MIT.txt` as provenance.

## Salesforce / SAP demo

Source: https://github.com/javierherrera1996/langgraph-salesforce-sap-demo (92 archive entries). Inspected tools for Salesforce, SAP and LLMs; lead/ticket graphs; state models; API routes; dependency declarations.

The Salesforce tools separate mock versus REST operations and provide task creation, owner assignment and data extraction. SAP tools use OData-shaped business partner and order records, sessions and CSRF tokens. Their mock IDs use Python hashes and data uses randomness, so they are unsuitable as stable cross-run ground truth without changes. Lead and ticket graphs fetch, enrich, score/classify, decide and execute writes. State is typed, with trace fields and separate LLM analyses. API routes validate input through Pydantic. The LLM layer attempts LangSmith Hub prompts and configures tracing at import time.

Adapted ideas: pure tool interfaces, typed business data, separate computed and model-generated analysis, API-driven workflows and inspectable traces. Newly implemented adapters use one coherent SQLite dataset, stable IDs, deterministic cents and no external side effects. Original auto-write stages are replaced by durable approval and transactional idempotency. No original source code is copied or imported.

Discarded: GCP/Vertex deployment scripts, experimental Lovable backend, automatic email integrations, automatic tracing/prompt downloads, random transient mock generators, generic lead scoring and ticket categorization outside renewal scope. The original pyproject requires Python 3.11 and broad unpinned LangChain/LangGraph ranges; a separate tested environment was resolved for this project.

License caveat: `pyproject.toml` declares MIT, but this supplied archive does not contain a standalone LICENSE file. We therefore reuse architectural ideas only and do not redistribute copied source in this project. Keep the extracted archive reference outside the application's distribution. Verify upstream licensing before any future source-code reuse.

## Result

This is a newly written application inspired by both architectures. Its runtime has no dependency on the extracted repositories. Attribution is explicit in README and THIRD_PARTY_NOTICES. Prepared Salesforce/Dynamics/SAP/Foundry read adapters now exist, but none is live verified. LangSmith is not integrated. See CONNECTORS.md for current scope. Raw source-archive manifests remain local and are not required to run the application.
