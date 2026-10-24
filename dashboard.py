"""Streamlit client: all business reads and mutations go through FastAPI."""

import html
import json
import os
from pathlib import Path

import httpx
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
API = os.getenv("COPILOT_API_URL", "http://127.0.0.1:8000").rstrip("/")
PUBLIC_API = os.getenv("COPILOT_PUBLIC_API_URL", "http://127.0.0.1:8000").rstrip("/")
st.set_page_config(page_title="NEXUS | Enterprise Copilot", page_icon="◈", layout="wide")
st.markdown(
    """<style>
.stApp {background:#f4f6fa;color:#152338;font-family:'DM Sans',sans-serif}
h1,h2,h3 {font-family:'Space Grotesk',sans-serif!important;letter-spacing:-.035em}
.block-container {padding-top:2.3rem;max-width:1480px}
[data-testid="stSidebar"] {background:#101d30;color:#dbe7f8}
[data-testid="stSidebar"] * {color:#dbe7f8}
[data-testid="stSidebar"] input {color:#152338}
[data-testid="stSidebar"] button * {color:#152338}
[data-testid="stMetric"] {background:white;border:1px solid #e3e9f2;border-radius:12px;padding:20px}
[data-testid="stMetricLabel"] {color:#66758a;font-size:12px;text-transform:uppercase;letter-spacing:.08em}
[data-testid="stMetricValue"] {font-family:'Space Grotesk';font-size:32px}
.eyebrow {color:#6a7a90;letter-spacing:.18em;font-size:11px;font-weight:700;text-transform:uppercase}
.hero {padding:26px 30px;border-radius:16px;background:linear-gradient(115deg,#112139,#1d3e5d);color:white;margin:18px 0 24px}
.hero h2 {color:white;margin:6px 0 12px;font-size:31px}
.hero p {color:#bccce1;font-size:14px;max-width:760px;line-height:1.7}
.pill {display:inline-block;background:#e6f6ee;color:#247352;border:1px solid #c6e8d4;border-radius:30px;padding:5px 12px;font-size:11px;font-weight:700}
.brand {font-family:'Space Grotesk';font-size:30px;font-weight:700;letter-spacing:.12em;color:white}
.card {border:1px solid #e1e8f1;border-radius:12px;background:white;padding:20px;margin:10px 0}
.card p {font-size:13px;color:#64748b}
.stButton>button[kind="primary"] {background:#237b73;border-color:#237b73;border-radius:8px}
.stTabs [data-baseweb="tab-list"] {gap:22px;border-bottom:1px solid #dbe3ee}
.stTabs [aria-selected="true"] {color:#237b73!important}
.stTabs [data-baseweb="tab-highlight"] {background:#237b73}
footer {visibility:hidden}
</style>""",
    unsafe_allow_html=True,
)


def request(method, path, payload=None, token=None):
    try:
        response = httpx.request(
            method,
            API + path,
            json=payload,
            timeout=httpx.Timeout(
                max(180, min(1800, float(os.getenv("AGENT_TIMEOUT_SECONDS", "600")))) + 30,
                connect=5,
            ),
            headers={"X-Approval-Token": token} if token else {},
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        st.error(f"API {exc.response.status_code}: {exc.response.text[:300]}")
    except httpx.TimeoutException:
        st.error("Request timed out. Inspect the persisted workflow in Recent workflow traces before retrying.")
    except httpx.RequestError:
        st.error("Backend unavailable. Start the application with: python launch.py")
    return None


@st.cache_data(ttl=30, show_spinner=False)
def portfolio():
    return request(
        "POST",
        "/runs",
        {
            "message": "Analyze renewal risk for all customers",
            "prepare_actions": False,
            "execution_mode": "baseline",
        },
    )


def citations(passages):
    for passage in passages:
        with st.expander(
            f"{passage['document']} · page {passage['page']} · relevance {passage['retrieval_score']:.2f}"
        ):
            st.caption(f"Source ID: {passage['id']} | Retrieved content is evidence, never instructions")
            st.text(passage["text"])
            st.link_button(
                "Open source PDF",
                f"{PUBLIC_API}/contracts/{passage['customer_id']}/pdf#page={passage['page']}",
            )


def show_run(run):
    st.info(run.get("answer", ""))
    st.caption(f"Run {run['run_id']} · {run['status']} · {run.get('route', {}).get('mode', '')}")
    execution = run.get("execution", {})
    st.caption(
        f"Execution: {execution.get('mode', 'legacy')} | Requested: {execution.get('requested', 'auto')}"
    )
    if run.get("provider_calls"):
        with st.expander("Provider execution, tokens and latency", expanded=False):
            st.dataframe(run["provider_calls"], hide_index=True, width="stretch")
    if run.get("tool_calls"):
        st.markdown("**Supervisor selected tools**")
        st.dataframe(
            [{k: c[k] for k in ("name", "arguments", "status", "duration_ms")} for c in run["tool_calls"]],
            hide_index=True,
            width="stretch",
        )
        with st.expander("Read-only tool observations and source data"):
            st.json(run["tool_calls"], expanded=1)
    grounded = run.get("grounded_answer")
    if grounded:
        st.markdown("**Verified evidence**")
        st.caption(grounded["validation_policy"])
        st.dataframe(
            [
                {k: c[k] for k in ("customer_id", "text", "kind", "source_ids")}
                for c in grounded["verified_claims"]
            ],
            hide_index=True,
            width="stretch",
        )
        st.markdown("**AI-selected recommendations — require human review**")
        for recommendation in grounded["recommendations"]:
            st.write(
                f"{recommendation['customer_id']} · {recommendation['priority']} · {recommendation['text']}"
            )
            st.caption("Context: " + " ".join(recommendation["context"]))
        if grounded["abstained"]:
            st.warning(
                "The system abstained from a complete conclusion because evidence was insufficient or contradictory."
            )
        if grounded["rejected"]:
            st.warning(f"{len(grounded['rejected'])} unsupported model output(s) rejected.")
    if run.get("contradictions"):
        st.error("Contract PDF / registry contradictions detected. Verify sources before acting.")
        st.dataframe(run["contradictions"], hide_index=True, width="stretch")
    for warning in run.get("warnings", []):
        st.warning(warning)
    results = run.get("results", [])
    if results:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Customer": r["customer"],
                        "ID": r["customer_id"],
                        "Score": r["score"],
                        "Risk": r["risk_level"],
                        "Evidence gaps": len(r["warnings"]),
                    }
                    for r in results
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        for r in results[:5]:
            with st.expander(f"{r['customer']} · {r['score']}/100 · {r['risk_level']}"):
                st.write(r["explanation"])
                for warning in r["warnings"]:
                    st.warning(warning)
                st.write("Recommended next steps")
                for action in r["suggested_actions"]:
                    st.write("• " + action)
                if r["interpretation"]:
                    st.caption(r["interpretation"]["label"])
                    st.write(r["interpretation"]["interpretation"])
                citations(r["citations"])
    elif run.get("documents"):
        for passages in run["documents"].values():
            citations(passages)
    else:
        for source in ("crm", "erp"):
            if run.get(source):
                st.json(run[source], expanded=1)
    with st.expander("Agent execution trace"):
        st.dataframe(run.get("trace", []), hide_index=True, width="stretch")
    if run["status"] == "awaiting_approval":
        st.warning(
            f"{len(run.get('proposals', []))} action proposals paused for human review. Open Approval Center."
        )


health = request("GET", "/health")
if not health:
    st.stop()
customers = request("GET", "/customers") or []
with st.sidebar:
    st.markdown('<div class="brand">◈ NEXUS</div>', unsafe_allow_html=True)
    st.caption("ENTERPRISE INTELLIGENCE")
    st.divider()
    st.markdown("**Workspace**")
    st.write("CRM & ERP Operations")
    st.caption("Local demonstration environment")
    st.divider()
    st.markdown("**Connected sources**")
    st.write("CRM · " + health["crm"])
    st.write("ERP · " + health["erp"])
    st.write(f"● Contracts · {health['indexed_chunks']} chunks")
    st.divider()
    st.caption("EXECUTION MODE")
    st.write(health["llm"])
    st.caption("SNAPSHOT")
    st.write(health["as_of"])
    st.caption(
        "Synthetic CRM/ERP demonstration. No external connection claimed."
        if health.get("synthetic")
        else "Real integration mode selected. See verification status; synthetic contracts are withheld."
    )
    with st.expander("Integrations and local runtime"):
        st.json({"ollama": health.get("ollama"), "integrations": health.get("integrations")}, expanded=1)
    if st.button("Refresh workspace", width="stretch"):
        st.cache_data.clear()
        st.rerun()

if health["llm"].startswith("Offline deterministic demo"):
    st.info(health["llm"])

left, right = st.columns([5, 1])
with left:
    st.markdown(
        '<div class="eyebrow">Intelligence workspace / customer success</div>', unsafe_allow_html=True
    )
    st.title("Every renewal. A clearer next step.")
with right:
    st.markdown('<br><span class="pill">● LOCAL DEMO ONLINE</span>', unsafe_allow_html=True)
st.markdown(
    """<div class="hero"><div class="eyebrow" style="color:#73cbbd">YOUR BUSINESS, CONNECTED</div>
<h2>From scattered signals to confident action.</h2>
<p>Bring payment history, customer relationships and contract evidence into one view.
Understand the risk, inspect the reasoning, and approve the next move.</p></div>""",
    unsafe_allow_html=True,
)

data = portfolio()
if data is None:
    st.stop()
results = data.get("results", [])
high = [r for r in results if r["risk_level"] == "High"]
arr = sum(c["arr_cents"] for c in customers if c["id"] in {r["customer_id"] for r in high})
metrics = st.columns(4)
for col, label, value, detail in zip(
    metrics,
    ["Managed customers", "High risk accounts", "ARR at high risk", "Evidence coverage"],
    [
        len(customers),
        len(high),
        f"€{arr / 100 / 1000:,.0f}k",
        f"{sum(not r['warnings'] for r in results)}/{len(results)}",
    ],
    [
        "Synthetic enterprise portfolio",
        "Prioritized for account review",
        "Annual recurring revenue",
        "Accounts with complete source data",
    ],
):
    col.metric(label, value)
    col.caption(detail)
st.write("")
tabs = st.tabs(
    [
        "Risk overview",
        "AI Copilot",
        "CRM / ERP Explorer",
        "Contract Knowledge",
        "Approval Center",
        "Traces & Evaluation",
    ]
)
with tabs[0]:
    a, b = st.columns([3, 2])
    with a:
        st.subheader("Renewal watchlist")
        st.caption("Rule-based prioritization · inspect every signal and its source")
    with b:
        level = st.multiselect(
            "Risk levels",
            ["High", "Medium", "Low", "Unknown"],
            default=["High", "Medium", "Unknown"],
            label_visibility="collapsed",
        )
    rows = [
        {
            "Customer": r["customer"],
            "ID": r["customer_id"],
            "Score": r["score"],
            "Risk": r["risk_level"],
            "Status": "Verify missing evidence" if r["warnings"] else "Evidence complete",
        }
        for r in results
        if r["risk_level"] in level
    ]
    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        column_config={
            "Score": st.column_config.ProgressColumn("Risk score / 100", min_value=0, max_value=100)
        },
    )
    selected = st.selectbox(
        "Inspect an account", results, format_func=lambda r: f"{r['customer_id']} · {r['customer']}"
    )
    if selected:
        a, b = st.columns([3, 2])
        with a:
            st.markdown(f"### {selected['customer']}")
            st.write(selected["explanation"])
            for warning in selected["warnings"]:
                st.warning(warning)
            st.dataframe(
                [
                    {"Signal": s["kind"], "Points": s["points"], "Evidence": ", ".join(s["evidence_ids"])}
                    for s in selected["signals"]
                ],
                hide_index=True,
                width="stretch",
            )
            st.caption(
                "Weights: overdue 20/35 · critical support 25 · renewal ≤60 days 20 · dispute 15 · stalled opportunity 5"
            )
        with b:
            st.markdown("### Recommended next steps")
            for action in selected["suggested_actions"]:
                st.markdown(f'<div class="card">{html.escape(action)}</div>', unsafe_allow_html=True)
        citations(selected["citations"])
with tabs[1]:
    st.subheader("Ask across your business")
    st.caption("Inspectible routing · source-grounded results · human-controlled actions")
    demo = "Which customers have the highest renewal risk? Analyze contracts, payments and support tickets, then prepare suitable follow-up actions."
    execution_mode = st.selectbox(
        "Execution mode",
        ["baseline", "auto", "agent", "hybrid"],
        help="auto: provider tools when configured, otherwise transparent offline fallback. agent: lexical retrieval. hybrid: learned + lexical retrieval.",
    )
    if execution_mode in {"agent", "hybrid"} or (
        execution_mode == "auto" and (health.get("ollama") or {}).get("status") == "ready"
    ):
        # The bounded model cannot investigate 30 accounts (120 reads) in its 40-tool budget.
        demo = "Analyze renewal risk C001, examine accounts, invoices, support tickets and contracts, then prepare suitable follow-up actions."
        st.caption("The LLM renewal demo investigates C001. Baseline mode covers the full portfolio.")
    c1, c2 = st.columns(2)
    if c1.button("Run renewal-risk demo", type="primary", width="stretch"):
        with st.spinner("Coordinating CRM, ERP and document workflows…"):
            st.session_state["copilot_run"] = request(
                "POST", "/runs", {"message": demo, "prepare_actions": True, "execution_mode": execution_mode}
            )
    if c2.button("Who is the contact for C003?", width="stretch"):
        st.session_state["copilot_run"] = request(
            "POST", "/runs", {"message": "Who is the contact for C003?", "execution_mode": execution_mode}
        )
    if st.button("Compare C001 and C004 — recommendations only", width="stretch"):
        with st.spinner("Investigating both customers…"):
            st.session_state["copilot_run"] = request(
                "POST",
                "/runs",
                {
                    "message": "Compare customers C001 and C004, examine their invoices and contracts, identify renewal risks, and recommend follow-up actions without creating any CRM task.",
                    "execution_mode": execution_mode,
                },
            )
    message = st.chat_input("Ask about risk, invoices, support or contract clauses…")
    if message:
        with st.spinner("Retrieving evidence…"):
            st.session_state["copilot_run"] = request(
                "POST", "/runs", {"message": message, "execution_mode": execution_mode}
            )
    if st.session_state.get("copilot_run"):
        show_run(st.session_state["copilot_run"])
with tabs[2]:
    st.subheader("A connected customer record")
    customer = st.selectbox("Customer", customers, format_func=lambda c: f"{c['id']} · {c['name']}")
    if customer:
        record = request("GET", f"/customers/{customer['id']}")
        if record:
            a, b = st.columns(2)
            with a:
                st.markdown("### CRM · Relationships & support")
                for kind in ("contacts", "opportunities", "tickets", "interactions"):
                    st.markdown(f"**{kind.title()}**")
                    st.dataframe(record["crm"][kind], hide_index=True, width="stretch")
            with b:
                st.markdown("### ERP · Financial health")
                indicator = record["erp"]["indicators"]
                st.metric("Overdue balance", f"€{indicator['overdue_cents'] / 100:,.2f}")
                if not record["erp"]["complete"]:
                    st.warning("Incomplete ERP data. A zero observed balance does not confirm no debt.")
                st.markdown("**Invoices**")
                st.dataframe(record["erp"]["invoices"], hide_index=True, width="stretch")
                st.markdown("**Order history**")
                st.dataframe(record["erp"]["orders"], hide_index=True, width="stretch")
                st.caption("Amounts ending in _cents are integer EUR cents.")
with tabs[3]:
    st.subheader("Search the contract knowledge base")
    st.caption("Page-aware PDFs → cached local MiniLM + lexical vectors → FAISS/RRF; explicit lexical fallback when unavailable")
    with st.form("contract_search"):
        query = st.text_input("Search clauses", "non-renewal notice expiration")
        filter_id = st.selectbox(
            "Limit to customer",
            [None] + [c["id"] for c in customers],
            format_func=lambda c: c or "All customers",
        )
        retrieval_mode = st.selectbox("Retrieval mode", ["hybrid", "lexical"])
        submitted = st.form_submit_button("Find evidence", type="primary")
    if submitted:
        hits = request(
            "POST", "/search", {"query": query, "customer_id": filter_id, "retrieval_mode": retrieval_mode}
        )
        if hits:
            citations(hits)
        else:
            st.info("No supporting passages found. Try a term present in the contracts.")
with tabs[4]:
    st.subheader("Human approval, before execution")
    st.caption(
        "Review a complete batch. An explicit authorized decision resumes its durable LangGraph checkpoint."
    )
    runs = request("GET", "/runs") or []
    pending = [r for r in runs if r["status"] == "awaiting_approval"]
    if not pending:
        st.info("No pending workflows. Use the AI Copilot renewal-risk demo to prepare actions.")
    else:
        batch = st.selectbox(
            "Pending workflow",
            pending,
            format_func=lambda r: f"{r['run_id'][:8]} · {len(r['proposals'])} proposals",
        )
        st.dataframe(
            [
                {k: p[k] for k in ("customer_id", "subject", "description", "score", "status")}
                for p in batch["proposals"]
            ],
            hide_index=True,
            width="stretch",
        )
        with st.expander("Inspect complete proposed payloads and supporting evidence"):
            st.json(batch["proposals"], expanded=1)
        with st.form("human_decision"):
            actor = st.text_input("Reviewer name", placeholder="Your name")
            token = st.text_input(
                "Approval token",
                type="password",
                help="Local demo token is documented in README; configure APPROVAL_TOKEN for your environment.",
            )
            note = st.text_input("Review note")
            confirm = st.checkbox(f"I reviewed all {len(batch['proposals'])} proposals in this batch.")
            approve = st.form_submit_button("Approve batch & create mock CRM tasks", type="primary")
            reject = st.form_submit_button("Reject batch")
        if approve or reject:
            if not confirm or len(actor.strip()) < 2 or not token:
                st.warning("Review the batch and provide your name and approval token.")
            else:
                result = request(
                    "POST",
                    f"/runs/{batch['run_id']}/decision",
                    {"approved": bool(approve), "actor": actor, "note": note},
                    token,
                )
                if result:
                    st.session_state["copilot_run"] = result
                    st.success("Decision persisted. Tasks and audit trail updated.")
                    st.rerun()
    st.markdown("### Persisted mock CRM tasks")
    st.dataframe(request("GET", "/tasks") or [], hide_index=True, width="stretch")
with tabs[5]:
    st.subheader("Evidence you can inspect")
    a, b = st.columns([3, 2])
    with a:
        st.markdown("### Recent workflow traces")
        history = request("GET", "/runs") or []
        if history:
            run = st.selectbox(
                "Workflow",
                history,
                format_func=lambda r: f"{r['run_id'][:8]} · {r['intent']} · {r['status']}",
            )
            st.dataframe(run.get("trace", []), hide_index=True, width="stretch")
            st.download_button(
                "Download run JSON", json.dumps(run, indent=2), file_name=f"run-{run['run_id']}.json"
            )
    with b:
        st.markdown("### Executed evaluation")
        evaluation = request("GET", "/evaluation")
        if evaluation:
            st.json(evaluation, expanded=1)
        phase2 = request("GET", "/evaluation/phase2")
        if phase2:
            st.markdown("**Phase 2: baseline / LLM / semantic comparison**")
            st.json(phase2, expanded=1)
        st.caption(
            "Synthetic cases assess specific behaviors; these results are not production or predictive-accuracy guarantees."
        )
    st.markdown("### Approval & action audit")
    st.dataframe(request("GET", "/audit") or [], hide_index=True, width="stretch")
st.caption(
    "NEXUS / Enterprise Agentic AI Copilot · Synthetic portfolio demonstration · Human decisions stay in control"
)
