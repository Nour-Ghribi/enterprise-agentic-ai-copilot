from datetime import date

from copilot.config import AS_OF
from copilot.models import CustomerLookup
from copilot.store import Store


def crm_lookup(store: Store, query: CustomerLookup) -> dict:
    cid = query.customer_id
    return {
        "customer": store.customer(cid),
        **{
            kind: store.records(kind, cid)
            for kind in ("tickets", "contacts", "opportunities", "interactions")
        },
        "source": "synthetic_mock_crm",
    }


def financials(invoices: list[dict], as_of: str = AS_OF) -> dict:
    today = date.fromisoformat(as_of)
    overdue = []
    for invoice in invoices:
        outstanding = invoice["amount_cents"] - invoice["paid_cents"]
        days = (today - date.fromisoformat(invoice["due_date"])).days
        if outstanding > 0 and days > 0:
            overdue.append(
                {"invoice_id": invoice["id"], "outstanding_cents": outstanding, "days_overdue": days}
            )
    return {
        "overdue_cents": sum(r["outstanding_cents"] for r in overdue),
        "max_days_overdue": max((r["days_overdue"] for r in overdue), default=0),
        "overdue_invoices": overdue,
        "billed_cents": sum(r["amount_cents"] for r in invoices),
        "currency": "EUR",
        "as_of": as_of,
    }


def erp_lookup(store: Store, query: CustomerLookup) -> dict:
    invoices = store.records("invoices", query.customer_id)
    return {
        "invoices": invoices,
        "orders": store.records("orders", query.customer_id),
        "indicators": financials(invoices),
        "complete": store.customer(query.customer_id)["erp_complete"],
        "source": "synthetic_mock_erp",
    }
