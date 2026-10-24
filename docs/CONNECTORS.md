# Prepared enterprise connectors - no live connection claimed

`copilot/integrations.py` contains read-only adapters selected by configuration. All enterprise credentials and endpoints in `.env.example` are blank. None was configured or contacted during this implementation. Default data remains coherent synthetic local CRM/ERP. No connector can create a remote task, send email or bypass approval.

| Adapter | Prepared behavior | Current live verification |
|---|---|---|
| Salesforce CRM | REST account GET, related contacts/opportunities/cases queries, limits probe; canonical account mapping | Not configured / not tested live |
| Microsoft Dynamics 365 | Dataverse v9.2 account GET, related contacts/opportunities/incidents, WhoAmI probe | Not configured / not tested live |
| SAP ERP | OData sales-order reads, open-item invoice normalization with explicit tenant field mapping, business-partner probe | Not configured / not tested live |
| Azure AI Foundry | OpenAI v1 model-list probe and optional compatible model transport; project endpoints are not inference endpoints | Not configured / not tested live |

## Mode selection

```dotenv
CRM_MODE=mock
CRM_PROVIDER=salesforce
ERP_MODE=mock
AZURE_FOUNDRY_MODE=mock
```

Set CRM_MODE=real and CRM_PROVIDER=salesforce or dynamics365 for the selected CRM; ERP_MODE=real selects SAP. Real mode without required configuration raises an explicit error/HTTP 503; it never substitutes synthetic data silently. Invalid mode values fail configuration validation. Switch back to mock to resume the unchanged local demonstration.

Salesforce: SALESFORCE_ENDPOINT, SALESFORCE_ACCESS_TOKEN and CRM_ID_MAP_PATH. Dynamics: DYNAMICS365_ENDPOINT, DYNAMICS365_ACCESS_TOKEN and CRM_ID_MAP_PATH. CRM_ID_MAP_PATH identifies a local JSON map from application IDs such as C001 to actual Salesforce IDs or Dynamics GUIDs. Example structure is in config/customer-id-map.example.json; replace empty values before real use.

`customer()` normalizes real account identity/name only and explicitly marks commercial completeness false; it does not invent ARR, contacts, opportunities or history. Lower-level related-read methods are provided, but complete tenant-specific commercial-history normalization remains unfinished. Ticket normalization additionally requires CRM_TICKET_SEVERITY_MAP and CRM_TICKET_STATUS_MAP (JSON mappings to critical/normal and open/closed); unsupported values fail rather than inventing risk signals. OAuth token acquisition/refresh, scopes and deployment permissions are not implemented.

SAP: SAP_ENDPOINT, SAP_ACCESS_TOKEN, ERP_ID_MAP_PATH, SAP_OPEN_ITEMS_PATH, SAP_INVOICE_FIELD_MAP and REAL_AS_OF_DATE. An invoice mapping must explicitly identify id, customer, amount, paid, due_date and currency fields in your tenant's open-item OData response. Sales-order/billing totals are not assumed to be unpaid balances. Normalization uses Decimal cents, validates customer and dates, rejects ambiguous overpayments and non-EUR rows, and does not use the fixed synthetic aging date for real finances. No generic production SAP schema compatibility is claimed.

Foundry endpoints/keys/model remain blank. For future deliberate use, AZURE_FOUNDRY_MODE=real enables prepared reads, and LLM_PROVIDER=foundry plus LLM_MODE=foundry selects the optional compatible inference client. Use an inference base ending `/openai/v1`, not a project URL; configure AZURE_FOUNDRY_ENDPOINT, AZURE_FOUNDRY_MODEL and AZURE_FOUNDRY_API_KEY. This is unused in the no-commercial-API local demo. Entra ID/project-management APIs are not implemented.

## Verification and safety

GET /integrations returns mock, unconfigured, configured_unverified or verified_read, with a timestamp and no credential values. Configuration alone never becomes a live connection. Successful HTTP fixtures never set live_verified. A real successful read verifies only that read, not the whole integration or business workflow; verification is process-local and resets after restart.

POST /integrations/{name}/probe requires the operator approval token. In mock mode it performs no external request. It is never exposed to the LLM tool list, never executed automatically, and was not invoked against an enterprise service here. Probes use HTTPS GET with redirects rejected. Pagination is bounded and restricted to the configured origin. External identifiers and response account identity are validated.

Synthetic contracts are withheld whenever real CRM/ERP mode is selected. A real customer contract corpus and full commercial normalization are not configured, so complete real-data risk analysis/CRM writes remain unavailable. Real adapters are read-only; mock tasks still require persistent human approval. The actual real operating pipeline needs tenant validation before use.

References: [Salesforce REST account retrieval](https://developer.salesforce.com/docs/platform/api-rest/guide/resources-sobject-retrieve-get.html), [Dataverse retrieval](https://learn.microsoft.com/en-gb/power-apps/developer/data-platform/webapi/retrieve-entity-using-web-api), [SAP Sales Order OData](https://help.sap.com/docs/SAP_S4HANA_CLOUD/03c04db2a7434731b7fe21dca77440da/17f4a94ed364458ba96b399d43fd1779.html), [Foundry v1 models](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/models).
