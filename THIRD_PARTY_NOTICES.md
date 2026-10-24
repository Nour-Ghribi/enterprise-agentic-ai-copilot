# Attribution

The optional pretrained `sentence-transformers/all-MiniLM-L6-v2` encoder runs through FastEmbed/ONNX Runtime. Model source: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 . Cached artifact hashes are published in [the portable manifest](reports/public/semantic-model-manifest.json); weights are excluded from Git and portable archives. No resource was downloaded in the 2026-10-24 finalization. Dependencies/model artifacts retain their upstream terms.

This project is a newly written implementation inspired by:

- **AzureCosmosDB/multi-agent-langgraph**, Microsoft Corporation: specialist agent handoffs, shared LangGraph state, vector retrieval and durable human interrupts. Source: https://github.com/AzureCosmosDB/multi-agent-langgraph . Supplied license: MIT; original notice retained in `licenses/Azure-MIT.txt`.
- **javierherrera1996/langgraph-salesforce-sap-demo**: CRM/SAP tool separation, mock adapters, typed business state and API-orchestrated workflows. Source: https://github.com/javierherrera1996/langgraph-salesforce-sap-demo . Its supplied pyproject declares MIT; no standalone LICENSE was present in that ZIP. No code was copied or redistributed in this application's runtime.

No source files from those archives are imported by this application. Their extracted references remain outside this project directory. Architectural inspiration should not be represented as an original invention or as a verified production integration.

Dependencies retain their own licenses and notices. `requirements-lock.txt` records resolved distributions; consult their distribution metadata for license terms.
