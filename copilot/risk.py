from datetime import date

from copilot.config import AS_OF


def analyze(
    customer: dict,
    crm: dict | None,
    erp: dict | None,
    contract: dict | None,
    citations: list[dict],
    as_of: str = AS_OF,
) -> dict:
    signals, warnings = [], []

    def add(kind, points, fact, evidence_ids, action):
        signals.append(
            {
                "kind": kind,
                "points": points,
                "fact": fact,
                "evidence_ids": evidence_ids,
                "suggested_action": action,
            }
        )

    if not erp or not erp.get("complete"):
        warnings.append("ERP data incomplete: unpaid balances cannot be ruled out.")
    if erp:
        financial = erp["indicators"]
        if financial["overdue_cents"]:
            points = 35 if financial["max_days_overdue"] > 60 else 20
            add(
                "overdue",
                points,
                f"EUR {financial['overdue_cents'] / 100:,.2f} overdue; oldest {financial['max_days_overdue']} days.",
                [r["invoice_id"] for r in financial["overdue_invoices"]],
                "Agree a payment recovery plan with finance.",
            )
    if not crm or not customer.get("crm_complete"):
        warnings.append("CRM history incomplete: support and commercial signals require verification.")
    if crm:
        critical = [
            t["id"] for t in crm["tickets"] if t["severity"] == "critical" and t["status"] != "closed"
        ]
        if critical:
            add(
                "critical_support",
                25,
                f"{len(critical)} unresolved critical support ticket(s).",
                critical,
                "Escalate critical incidents to the support lead.",
            )
        stalled = [o["id"] for o in crm["opportunities"] if o["stage"] == "Stalled"]
        if stalled:
            add(
                "stalled_opportunity",
                5,
                "Renewal opportunity is stalled.",
                stalled,
                "Arrange an account-owner review with procurement.",
            )
    if not contract or not contract.get("expiry"):
        warnings.append("Contract expiration is missing; confirm renewal dates before acting.")
    else:
        remaining = (date.fromisoformat(contract["expiry"]) - date.fromisoformat(as_of)).days
        if remaining <= 60:
            add(
                "renewal_window",
                20,
                f"Contract expires {contract['expiry']} ({remaining} days from snapshot).",
                [contract["id"]],
                "Confirm renewal intent and notice deadline with procurement.",
            )
        if contract["dispute"]:
            add(
                "contract_dispute",
                15,
                "Contract registry records an unresolved contractual dispute.",
                [contract["id"]],
                "Request legal review of the documented service-credit dispute.",
            )
    if not citations:
        warnings.append(
            "No contract passages retrieved. Contract registry signals have no PDF corroboration."
        )
    score = sum(s["points"] for s in signals)
    level = "High" if score >= 60 else "Medium" if score >= 25 else "Low"
    if warnings:
        level = "Unknown" if score < 25 else level
    explanation = " ".join(s["fact"] for s in signals) or "No elevated signals observed in available records."
    return {
        "customer_id": customer["id"],
        "customer": customer["name"],
        "score": score,
        "risk_level": level,
        "score_is_lower_bound": bool(warnings),
        "signals": signals,
        "evidence": signals,
        "citations": citations,
        "warnings": warnings,
        "explanation": explanation,
        "suggested_actions": [s["suggested_action"] for s in signals] or ["Continue routine account review."],
        "interpretation": None,
        "explanation_mode": "deterministic evidence summary",
        "as_of": as_of,
        "synthetic": bool(customer.get("synthetic", True)),
    }
