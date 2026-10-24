# Phase 2 demonstrations

## Main: compare without writes

Ask: Compare customers C001 and C004, examine their invoices and contracts, identify renewal risks, and recommend follow-up actions without creating any CRM task.

Select hybrid mode. With a provider configured, the supervisor can choose account, invoice, ticket and contract tools for both IDs, inspect observations and output verified facts/citations plus AI-selected actions. The script/test expectation is score 85 for C001 and 40 for C004. No proposal or CRM task is allowed. Inspect per-run execution label: without a key the app falls back to offline rules, while learned retrieval can still be real.

## Selective tools

Who is the contact for C003? A provider can answer using only get_customer. Show invoices for C001 can use only get_invoices. The local tests exercise both paths with labeled HTTP fixtures; live-provider selection remains pending.

## Semantic document question

Search urgent outage acknowledgement for C003, comparing lexical and hybrid. Lexical has no matching term; hybrid retrieves page 2 using actual MiniLM embeddings. With a configured provider, ask about the critical-incident response requirement: the answer must select the exact supported 4-hour clause and carry its PDF/page citation. Without a provider, the search returns passages without claiming generated reasoning.

## Contradiction and unsupported assertion

The tests replace C001's PDF expiration by 2099-12-31 in a temporary database. The system detects disagreement with registry expiration 2026-11-15, retains registry score 85 and abstains from a complete conclusion/proposal. A simulated output claiming bankruptcy with a real invoice ID is rejected because text and canonical fact do not match. These are development tests, not claims of comprehensive legal or adversarial robustness.

## Approval remains durable

Use the original prepare-actions demo, review all payloads, and approve/reject with reviewer name and token. The graph pauses through interrupt, resumes through Command and persists through SqliteSaver. Local default token: local-demo-approver. Repeating an approved identical task does not create another. No provider or PDF can approve a task.

Validation commands are in README. Real-provider validation uses a temporary database and the no-write main request; the report is pending_credentials until a key is provided.
