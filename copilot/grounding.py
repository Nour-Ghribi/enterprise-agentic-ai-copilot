"""Closed-world factual claims: exact canonical facts, never arbitrary model prose.

This deliberately trades unrestricted paraphrasing for auditable correspondence.
It does not claim to solve general natural-language entailment.
"""

import re

from copilot.models import GroundedDraft

ACTION_TEXT = {
    "payment_plan": "Agree a payment recovery plan with finance.",
    "support_escalation": "Escalate critical incidents to the support lead.",
    "renewal_review": "Confirm renewal intent and notice deadline with procurement.",
    "legal_review": "Request legal review of the documented service-credit dispute.",
    "verify_data": "Verify missing or contradictory source data before proceeding.",
}


def fact(fact_id, cid, text, source_ids, kind="record", predicate="", value=None, citation=None):
    return {
        "fact_id": fact_id,
        "customer_id": cid,
        "text": text,
        "source_ids": source_ids,
        "kind": kind,
        "predicate": predicate,
        "value": value,
        "citation": citation,
    }


def build_facts(state):
    catalogue = {}

    def put(item):
        catalogue[item["fact_id"]] = item

    for cid, crm in state.get("crm", {}).items():
        if crm.get("customer"):
            customer = crm["customer"]
            put(
                fact(
                    cid + ":name",
                    cid,
                    f"{cid}: {customer['name']}.",
                    [cid],
                    predicate="name",
                    value=customer["name"],
                )
            )
        for contact in crm.get("contacts", []):
            put(
                fact(
                    contact["id"],
                    cid,
                    f"Contact for {cid}: {contact['name']} ({contact['email']}).",
                    [contact["id"]],
                )
            )
        if crm.get("tickets_fetched"):
            critical = [
                t["id"]
                for t in crm.get("tickets", [])
                if t["severity"] == "critical" and t["status"] != "closed"
            ]
            put(
                fact(
                    cid + ":critical",
                    cid,
                    f"{cid} has {len(critical)} unresolved critical support ticket(s).",
                    critical or [cid + ":tickets_snapshot"],
                    "calculated",
                    "critical_count",
                    len(critical),
                )
            )
            for ticket in crm.get("tickets", []):
                put(
                    fact(
                        ticket["id"],
                        cid,
                        f"{ticket['id']}: severity {ticket['severity']}, status {ticket['status']}.",
                        [ticket["id"]],
                        predicate="ticket_status",
                        value=ticket["status"],
                    )
                )
    for cid, erp in state.get("erp", {}).items():
        indicators = erp["indicators"]
        put(
            fact(
                cid + ":overdue",
                cid,
                f"{cid} has EUR {indicators['overdue_cents'] / 100:,.2f} overdue in available invoices.",
                [i["id"] for i in erp["invoices"]] or [cid + ":invoices_snapshot"],
                "calculated",
                "overdue_cents",
                indicators["overdue_cents"],
            )
        )
        for invoice in erp["invoices"]:
            put(
                fact(
                    invoice["id"],
                    cid,
                    f"{invoice['id']}: EUR {invoice['amount_cents'] / 100:,.2f} billed, EUR {invoice['paid_cents'] / 100:,.2f} paid; due {invoice['due_date']}.",
                    [invoice["id"]],
                    predicate="invoice",
                    value=invoice["amount_cents"],
                )
            )
    for cid, contracts in state.get("registers", {}).items():
        for contract in contracts:
            put(
                fact(
                    contract["id"] + ":expiry",
                    cid,
                    f"Registry expiration for {cid}: {contract['expiry'] or 'unknown'}.",
                    [contract["id"]],
                    predicate="expiry",
                    value=contract["expiry"],
                )
            )
            put(
                fact(
                    contract["id"] + ":dispute",
                    cid,
                    f"Registry contractual dispute for {cid}: {contract['dispute']}.",
                    [contract["id"]],
                    predicate="dispute",
                    value=contract["dispute"],
                )
            )
    for cid, passages in state.get("documents", {}).items():
        for passage in passages:
            for n, line in enumerate(passage["text"].splitlines()):
                if len(line.strip()) < 12 or line.startswith(("SYNTHETIC", "Customer:")):
                    continue
                citation = {k: passage[k] for k in ("id", "document", "page", "source_sha256")}
                put(
                    fact(
                        passage["id"] + f":line{n}",
                        cid,
                        line.strip(),
                        [passage["id"]],
                        "document",
                        "clause",
                        line.strip(),
                        citation,
                    )
                )
    for result in state.get("results", []):
        cid = result["customer_id"]
        put(
            fact(
                cid + ":score",
                cid,
                f"{cid}: observed risk score {result['score']}/100 ({result['risk_level']}).",
                [ref for s in result["signals"] for ref in s["evidence_ids"]],
                "calculated",
                "score",
                result["score"],
            )
        )
        for signal in result["signals"]:
            put(
                fact(
                    cid + ":signal:" + signal["kind"],
                    cid,
                    signal["fact"],
                    signal["evidence_ids"],
                    "calculated",
                    signal["kind"],
                    True,
                )
            )
        for n, warning in enumerate(result["warnings"]):
            put(fact(cid + f":warning:{n}", cid, warning, [cid], "validation", "missing", True))
    return catalogue


def contradictions(registers, passages):
    problems = []
    for registry in registers:
        for passage in passages:
            text = passage["text"]
            dates = re.findall(r"(?:contract\s+)?expir(?:ation|y)\s*:\s*(\d{4}-\d{2}-\d{2})", text, re.I)
            notices = re.findall(r"(?:notice\s*:\s*|notice[^.\n]{0,40}?)(\d+)\s*days", text, re.I)
            for field, values in [("expiry", dates), ("notice_days", [int(v) for v in notices])]:
                for value in values:
                    if registry.get(field) is not None and registry[field] != value:
                        problems.append(
                            {
                                "customer_id": registry["customer_id"],
                                "field": field,
                                "registry_value": registry[field],
                                "pdf_value": value,
                                "document": passage["document"],
                                "page": passage["page"],
                                "source_id": passage["id"],
                            }
                        )
            if re.search(r"no contractual dispute|no dispute", text, re.I) and registry.get("dispute"):
                problems.append(
                    {
                        "customer_id": registry["customer_id"],
                        "field": "dispute",
                        "registry_value": True,
                        "pdf_value": False,
                        "document": passage["document"],
                        "page": passage["page"],
                        "source_id": passage["id"],
                    }
                )
            if re.search(r"unresolved[^.\n]{0,40}dispute", text, re.I) and not registry.get("dispute"):
                problems.append(
                    {
                        "customer_id": registry["customer_id"],
                        "field": "dispute",
                        "registry_value": False,
                        "pdf_value": True,
                        "document": passage["document"],
                        "page": passage["page"],
                        "source_id": passage["id"],
                    }
                )
    return problems


def validate_draft(draft: GroundedDraft, facts, allowed_customers):
    verified, rejected, recommendations = [], [], []
    for claim in draft.claims:
        source = facts.get(claim.fact_id)
        if (
            not source
            or source["customer_id"] != claim.customer_id
            or claim.customer_id not in allowed_customers
            or claim.text != source["text"]
        ):
            rejected.append(
                {
                    "type": "claim",
                    "reason": "Unsupported claim, altered text or wrong customer",
                    **claim.model_dump(),
                }
            )
        else:
            verified.append(source)
    allowed_predicates = {
        "payment_plan": {"overdue_cents", "overdue"},
        "support_escalation": {"critical_count", "critical_support"},
        "renewal_review": {"expiry", "renewal_window", "stalled_opportunity"},
        "legal_review": {"dispute", "contract_dispute"},
        "verify_data": {"missing"},
    }
    for recommendation in draft.recommendations:
        sources = [facts.get(i) for i in recommendation.based_on]
        valid = (
            recommendation.customer_id in allowed_customers
            and all(s and s["customer_id"] == recommendation.customer_id for s in sources)
            and any(
                s and s["predicate"] in allowed_predicates[recommendation.action] and s["value"]
                for s in sources
            )
        )
        if valid:
            recommendations.append(
                {
                    **recommendation.model_dump(),
                    "text": ACTION_TEXT[recommendation.action],
                    "label": "AI-selected recommendation; not a factual claim",
                    "context": [s["text"] for s in sources],
                }
            )
        else:
            rejected.append(
                {
                    "type": "recommendation",
                    "reason": "Action lacks applicable customer evidence",
                    **recommendation.model_dump(),
                }
            )
    return {
        "verified_claims": verified,
        "recommendations": recommendations,
        "rejected": rejected,
        "abstained": draft.abstain or not verified,
        "validation_policy": "Exact canonical fact correspondence v1",
    }
