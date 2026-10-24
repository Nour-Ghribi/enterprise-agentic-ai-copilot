"""Reproducible, fictional business data. Never reads or writes an external CRM."""

import json
from datetime import date, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from copilot.config import AS_OF
from copilot.store import Store

NAMES = [
    "Atlas Industries",
    "Carthage Logistics",
    "Olive Technologies",
    "Medina Retail",
    "Sahara Energy",
    "Jasmine Telecom",
    "Horizon Manufacturing",
    "Delta Healthcare",
    "Cedar Financial",
    "Sirocco Transport",
    "Nova Aerospace",
    "Coral Hospitality",
    "Meridian Foods",
    "Oasis Pharma",
    "Falcon Automotive",
    "Prism Insurance",
    "Lighthouse Media",
    "Amber Chemicals",
    "Vega Construction",
    "Summit Textiles",
    "Bluewater Shipping",
    "Palm Agriculture",
    "Aurora Electronics",
    "Granite Mining",
    "Pearl Consulting",
    "Vertex Education",
    "Mosaic Packaging",
    "Orion Utilities",
    "Acacia Systems",
    "Zenith Distribution",
]


def seed(store: Store):
    if store.customers():
        return
    today = date.fromisoformat(AS_OF)
    pdf_dir = store.directory / "contracts"
    pdf_dir.mkdir(exist_ok=True)
    with store.connect() as db:
        for n, name in enumerate(NAMES, 1):
            cid = f"C{n:03}"
            scenario = n if n <= 5 else (n % 5 + 1)
            expiry = (
                None
                if n == 5
                else (today + timedelta(days={1: 25, 2: 18, 3: 240, 4: 45, 5: 150}[scenario])).isoformat()
            )
            customer = {
                "id": cid,
                "name": name,
                "sector": ["Industry", "Services", "Technology"][n % 3],
                "owner": ["Amira Ben Ali", "Sami Mansour", "Leila Haddad"][n % 3],
                "arr_cents": (60000 + n * 3000) * 100,
                "currency": "EUR",
                "synthetic": True,
                "erp_complete": n != 5,
                "crm_complete": n != 5,
            }
            db.execute("INSERT INTO customers VALUES(?,?)", (cid, json.dumps(customer)))

            def record(kind, row):
                row = {**row, "customer_id": cid, "synthetic": True}
                db.execute("INSERT INTO records VALUES(?,?,?,?)", (row["id"], kind, cid, json.dumps(row)))

            dispute = scenario == 4
            record(
                "contracts",
                {
                    "id": f"CON-{cid}",
                    "expiry": expiry,
                    "notice_days": 60,
                    "dispute": dispute,
                    "document": f"contract-{cid}.pdf",
                },
            )
            record(
                "contacts",
                {
                    "id": f"CT-{cid}",
                    "name": f"Procurement Contact {n}",
                    "email": f"procurement.{n}@example.invalid",
                    "role": "Contract owner",
                },
            )
            record(
                "opportunities",
                {
                    "id": f"OP-{cid}",
                    "stage": "Stalled" if scenario in (1, 4) else "Negotiation",
                    "value_cents": customer["arr_cents"],
                    "kind": "Renewal",
                },
            )
            for j in range(2):
                record(
                    "interactions",
                    {
                        "id": f"INT-{cid}-{j}",
                        "date": (today - timedelta(days=10 + j * 20)).isoformat(),
                        "summary": "Contract service-credit dispute awaiting legal review."
                        if dispute
                        else "Renewal review scheduled with procurement.",
                        "channel": "meeting",
                    },
                )
                record(
                    "orders",
                    {
                        "id": f"SO-{cid}-{j}",
                        "date": (today - timedelta(days=30 + 60 * j)).isoformat(),
                        "amount_cents": 1200000 + n * 10000,
                        "currency": "EUR",
                        "status": "delivered",
                    },
                )
            if n != 5:
                for j in range(3):
                    overdue = scenario == 1 and j < 2
                    record(
                        "invoices",
                        {
                            "id": f"INV-{cid}-{j}",
                            "amount_cents": 500000 + n * 10000,
                            "paid_cents": 0 if overdue else 500000 + n * 10000,
                            "due_date": (
                                today - timedelta(days=75 + j * 15)
                                if overdue
                                else today - timedelta(days=5 + j * 30)
                            ).isoformat(),
                            "currency": "EUR",
                        },
                    )
            for j in range(3):
                record(
                    "tickets",
                    {
                        "id": f"TKT-{cid}-{j}",
                        "severity": "critical" if scenario == 1 and j == 0 else "normal",
                        "status": "open" if scenario in (1, 4) else "closed",
                        "subject": "Production integration unavailable"
                        if scenario == 1 and j == 0
                        else "Service request",
                        "opened": (today - timedelta(days=8 + j * 7)).isoformat(),
                    },
                )
            canvas = Canvas(str(pdf_dir / f"contract-{cid}.pdf"), pagesize=A4)
            canvas.setTitle(f"SYNTHETIC contract {cid}")
            pages = [
                [
                    "SYNTHETIC DEMONSTRATION CONTRACT - NOT LEGAL ADVICE",
                    f"Customer: {cid} | {name}",
                    "Section 1 - Renewal and termination",
                    f"Contract expiration: {expiry or 'UNKNOWN - metadata missing'}.",
                    "Written non-renewal notice is required 60 days before expiration.",
                    "Commercial review must confirm renewal intent with the customer.",
                ],
                [
                    "SYNTHETIC DEMONSTRATION CONTRACT",
                    f"Customer: {cid} | {name}",
                    "Section 2 - Service levels and payment",
                    "Invoices are payable within 30 days of issue.",
                    "Critical incidents require a response within 4 hours.",
                    "Service credits require a documented claim and review.",
                    "Section 3 - Contractual dispute status",
                    "Unresolved service-credit dispute; legal review pending."
                    if dispute
                    else "No contractual dispute is recorded in this synthetic snapshot.",
                ],
            ]
            for lines in pages:
                canvas.setFont("Helvetica", 10)
                for i, line in enumerate(lines):
                    canvas.drawString(42, 790 - i * 28, line)
                canvas.showPage()
            canvas.save()
        Store.audit(db, "synthetic_seed", {"as_of": AS_OF, "customers": 30})


if __name__ == "__main__":
    from copilot.config import DATA

    seed(Store(DATA))
    print(f"Synthetic dataset ready: {DATA}")
