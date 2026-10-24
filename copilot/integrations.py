"""Prepared read-only enterprise adapters. Configuration is never called verification.

No adapter creates remote records; mock approvals remain separate local transactions.
OAuth token acquisition/refresh and tenant-specific SAP schemas are operator responsibilities.
"""

import json
import os
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from copilot.models import CustomerLookup
from copilot.tools import crm_lookup, erp_lookup, financials


class IntegrationUnavailable(RuntimeError):
    pass


def mode(name):
    value = os.getenv(name, "mock")
    if value not in {"mock", "real"}:
        raise ValueError(f"{name} must be mock or real")
    return value


def cents(value):
    try:
        number = Decimal(str(value)) * 100
        if not number.is_finite() or number != number.to_integral_value() or number < 0:
            raise ValueError("Amount must have at most two decimals and be nonnegative")
        return int(number)
    except InvalidOperation as exc:
        raise ValueError("Invalid monetary value") from exc


class RemoteReadAdapter:
    def __init__(self, name, prefix):
        self.name, self.prefix = name, prefix
        self.endpoint = os.getenv(prefix + "_ENDPOINT", "").rstrip("/")
        self.token = os.getenv(prefix + "_ACCESS_TOKEN", "")
        self.transport = None
        self.verified = None
        self.last_error = None

    def status(self, selected_mode="real"):
        configured = bool(self.endpoint and self.token)
        return {
            "provider": self.name,
            "mode": selected_mode,
            "status": "mock"
            if selected_mode == "mock"
            else "verified_read"
            if self.verified
            else "configured_unverified"
            if configured
            else "unconfigured",
            "configured": configured,
            "live_verified": self.verified is not None,
            "verified_at_utc": self.verified,
            "last_error": self.last_error,
            "remote_writes_supported": False,
        }

    def get(self, path, params=None):
        if not self.endpoint or not self.token:
            raise IntegrationUnavailable(f"{self.name}: endpoint/token not configured; no mock substitution")
        parsed = urlparse(self.endpoint)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise IntegrationUnavailable("Remote connector requires a credential-free HTTPS base URL")
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Only fixed same-origin relative paths are permitted")
        try:
            with httpx.Client(timeout=15, follow_redirects=False, transport=self.transport) as client:
                response = client.get(
                    self.endpoint + path,
                    headers={"Authorization": "Bearer " + self.token, "Accept": "application/json"},
                    params=params,
                )
                if 300 <= response.status_code < 400:
                    raise IntegrationUnavailable("Redirect rejected to protect connector credentials")
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object from connector")
            # A mock HTTP transport is never a verified real connection.
            if self.transport is None:
                self.verified = datetime.now(timezone.utc).isoformat()
            self.last_error = None
            return payload
        except (httpx.HTTPError, ValueError, IntegrationUnavailable) as exc:
            self.verified = None
            self.last_error = type(exc).__name__
            raise IntegrationUnavailable(f"{self.name} read failed ({type(exc).__name__})") from exc

    def pages(self, path, params=None, flavour="odata"):
        records = []
        for _ in range(10):
            data = self.get(path, params)
            if flavour == "salesforce":
                records.extend(data.get("records", []))
                next_link = data.get("nextRecordsUrl")
            else:
                content = data.get("d", data)
                records.extend(content.get("results", content.get("value", [])))
                next_link = content.get("__next") or data.get("@odata.nextLink")
            if not next_link:
                return records
            full = urlparse(urljoin(self.endpoint + path, next_link))
            if (full.scheme, full.netloc) != (urlparse(self.endpoint).scheme, urlparse(self.endpoint).netloc):
                raise IntegrationUnavailable("Cross-origin pagination rejected")
            path = full.path + ("?" + full.query if full.query else "")
            params = None
        raise IntegrationUnavailable("Pagination limit reached; incomplete data is not treated as complete")


class SalesforceConnector(RemoteReadAdapter):
    def __init__(self):
        super().__init__("salesforce", "SALESFORCE")
        self.version = os.getenv("SALESFORCE_API_VERSION", "v66.0")
        if not re.fullmatch(r"v\d{2,3}\.\d", self.version):
            raise ValueError("Invalid Salesforce REST version")

    def validate_id(self, external_id):
        if not re.fullmatch(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?", external_id):
            raise ValueError("Invalid Salesforce account ID")

    def account(self, external_id):
        self.validate_id(external_id)
        result = self.get(
            f"/services/data/{self.version}/sobjects/Account/{external_id}", {"fields": "Id,Name,OwnerId"}
        )
        if str(result.get("Id", ""))[:15] != external_id[:15] or not result.get("Name"):
            raise IntegrationUnavailable("Salesforce account identity/schema mismatch")
        return result

    def related(self, external_id, kind):
        self.validate_id(external_id)
        queries = {
            "contacts": "SELECT Id,Name,Email FROM Contact",
            "tickets": "SELECT Id,Subject,Priority,Status,IsClosed FROM Case",
            "opportunities": "SELECT Id,Name,StageName,Amount FROM Opportunity",
        }
        if kind not in queries:
            raise ValueError("Unsupported related collection")
        return self.pages(
            f"/services/data/{self.version}/query",
            {"q": queries[kind] + f" WHERE AccountId = '{external_id}'"},
            "salesforce",
        )

    def probe(self):
        return self.get(f"/services/data/{self.version}/limits")


class Dynamics365Connector(RemoteReadAdapter):
    def __init__(self):
        super().__init__("dynamics365", "DYNAMICS365")

    def validate_id(self, external_id):
        if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", external_id):
            raise ValueError("Invalid Dynamics account GUID")

    def account(self, external_id):
        self.validate_id(external_id)
        result = self.get(
            f"/api/data/v9.2/accounts({external_id})", {"$select": "accountid,name,_ownerid_value"}
        )
        if str(result.get("accountid", "")).casefold() != external_id.casefold() or not result.get("name"):
            raise IntegrationUnavailable("Dynamics account identity/schema mismatch")
        return result

    def related(self, external_id, kind):
        self.validate_id(external_id)
        collections = {
            "contacts": ("contacts", "_parentcustomerid_value", "contactid,fullname,emailaddress1"),
            "tickets": ("incidents", "_customerid_value", "incidentid,title,severitycode,statecode"),
            "opportunities": ("opportunities", "_parentaccountid_value", "opportunityid,name,statecode"),
        }
        collection, foreign_key, fields = collections[kind]
        return self.pages(
            "/api/data/v9.2/" + collection, {"$select": fields, "$filter": foreign_key + " eq " + external_id}
        )

    def probe(self):
        return self.get("/api/data/v9.2/WhoAmI")


class SAPConnector(RemoteReadAdapter):
    def __init__(self):
        super().__init__("sap", "SAP")

    def orders(self, external_id):
        if not re.fullmatch(r"[A-Za-z0-9]{1,20}", external_id):
            raise ValueError("Invalid SAP customer ID")
        return self.pages(
            "/sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder",
            {"$filter": "SoldToParty eq '" + external_id + "'", "$format": "json"},
        )

    def invoices(self, external_id, cid):
        # Open-item APIs differ between SAP deployments. No billing total is invented as an unpaid balance.
        path = os.getenv("SAP_OPEN_ITEMS_PATH", "")
        fields = json.loads(os.getenv("SAP_INVOICE_FIELD_MAP", "{}") or "{}")
        required = {"id", "customer", "amount", "paid", "due_date", "currency"}
        if not path or not required <= fields.keys():
            raise IntegrationUnavailable("SAP open-items path and explicit invoice field mapping required")
        if not re.fullmatch(r"[A-Za-z0-9]{1,20}", external_id) or any(
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fields[k]) for k in required
        ):
            raise ValueError("Invalid SAP OData filter field or customer identifier")
        rows = self.pages(
            path, {"$filter": fields["customer"] + " eq '" + external_id + "'", "$format": "json"}
        )
        normalized = []
        for row in rows:
            if not {fields[k] for k in required} <= row.keys():
                raise IntegrationUnavailable("SAP response does not match the configured invoice schema")
            if str(row[fields["customer"]]) != external_id or row[fields["currency"]] != "EUR":
                raise IntegrationUnavailable(
                    "SAP customer/currency mismatch; no mixed-currency EUR total permitted"
                )
            due = str(row[fields["due_date"]])
            if due.startswith("/Date("):
                match = re.fullmatch(r"/Date\((\d+)(?:[+-]\d+)?\)/", due)
                if not match:
                    raise ValueError("Invalid SAP date")
                due = datetime.fromtimestamp(int(match[1]) / 1000, timezone.utc).date().isoformat()
            else:
                due = date.fromisoformat(due[:10]).isoformat()
            amount, paid = cents(row[fields["amount"]]), cents(row[fields["paid"]])
            if paid > amount:
                raise ValueError("Overpayment requires explicit accounting treatment")
            normalized.append(
                {
                    "id": str(row[fields["id"]]),
                    "customer_id": cid,
                    "amount_cents": amount,
                    "paid_cents": paid,
                    "due_date": due,
                    "currency": "EUR",
                    "synthetic": False,
                }
            )
        return normalized

    def probe(self):
        return self.get(
            "/sap/opu/odata/sap/API_BUSINESS_PARTNER/A_BusinessPartner", {"$top": 1, "$format": "json"}
        )


class FoundryConnector(RemoteReadAdapter):
    def __init__(self):
        super().__init__("azure_foundry", "AZURE_FOUNDRY")
        self.token = os.getenv("AZURE_FOUNDRY_API_KEY", "")

    def probe(self):
        if not self.endpoint.endswith("/openai/v1"):
            raise IntegrationUnavailable(
                "Foundry requires an OpenAI v1 inference base, not a project endpoint"
            )
        return self.get("/models")


class IntegrationHub:
    def __init__(self, store):
        self.store = store
        self.crm_mode, self.erp_mode = mode("CRM_MODE"), mode("ERP_MODE")
        self.foundry_mode = mode("AZURE_FOUNDRY_MODE")
        self.crm_provider = os.getenv("CRM_PROVIDER", "salesforce")
        if self.crm_provider not in {"salesforce", "dynamics365"}:
            raise ValueError("CRM_PROVIDER must be salesforce or dynamics365")
        self.adapters = {
            "salesforce": SalesforceConnector(),
            "dynamics365": Dynamics365Connector(),
            "sap": SAPConnector(),
            "azure_foundry": FoundryConnector(),
        }

    @property
    def fully_mock(self):
        return self.crm_mode == self.erp_mode == "mock"

    def mapping(self, domain):
        path = os.getenv(domain + "_ID_MAP_PATH", "")
        if not path:
            raise IntegrationUnavailable(domain + " canonical-to-external ID mapping is not configured")
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise IntegrationUnavailable(domain + " ID map cannot be read/parsed") from exc
        if not isinstance(data, dict) or any(
            not re.fullmatch(r"C\d{3}", key) or not isinstance(value, str) for key, value in data.items()
        ):
            raise ValueError("Invalid canonical customer mapping")
        return data

    def external_id(self, domain, cid):
        try:
            return self.mapping(domain)[cid]
        except KeyError as exc:
            raise IntegrationUnavailable("Customer not mapped to real integration") from exc

    def statuses(self):
        return {
            name: adapter.status(
                self.foundry_mode
                if name == "azure_foundry"
                else self.erp_mode
                if name == "sap"
                else self.crm_mode
                if name == self.crm_provider
                else "mock"
            )
            for name, adapter in self.adapters.items()
        }

    def customers(self, search=""):
        if self.crm_mode == "mock":
            return self.store.customers(search)
        result = []
        for cid in self.mapping("CRM"):
            account = self.customer(cid)["customer"]
            if search.casefold() in (account["name"] + " " + cid).casefold():
                result.append(account)
        return result

    def customer(self, cid):
        if self.crm_mode == "mock":
            return crm_lookup(self.store, CustomerLookup(customer_id=cid))
        adapter = self.adapters[self.crm_provider]
        external_id = self.external_id("CRM", cid)
        account = adapter.account(external_id)
        name = account["Name"] if self.crm_provider == "salesforce" else account["name"]
        return {
            "customer": {
                "id": cid,
                "name": name,
                "external_id": external_id,
                "crm_complete": False,
                "erp_complete": False,
                "synthetic": False,
                "owner": "Not normalized",
                "arr_cents": None,
                "currency": None,
                "sector": "Not normalized",
            },
            "contacts": [],
            "opportunities": [],
            "interactions": [],
            "tickets": [],
            "source": self.crm_provider,
            "limitations": ["Commercial history, contacts and opportunity mapping require tenant validation"],
        }

    def tickets(self, cid):
        if self.crm_mode == "mock":
            return self.store.records("tickets", cid)
        severity_map = json.loads(os.getenv("CRM_TICKET_SEVERITY_MAP", "{}") or "{}")
        status_map = json.loads(os.getenv("CRM_TICKET_STATUS_MAP", "{}") or "{}")
        if not severity_map or not status_map:
            raise IntegrationUnavailable("Explicit CRM severity/status normalization maps required")
        if not set(severity_map.values()) <= {"critical", "normal"} or not set(status_map.values()) <= {
            "open",
            "closed",
        }:
            raise ValueError("Invalid normalized ticket severity/status")
        rows = self.adapters[self.crm_provider].related(self.external_id("CRM", cid), "tickets")
        result = []
        sf = self.crm_provider == "salesforce"
        for row in rows:
            severity = str(row["Priority"] if sf else row["severitycode"])
            status = str(row["Status"] if sf else row["statecode"])
            if severity not in severity_map or status not in status_map:
                raise IntegrationUnavailable(
                    "Unmapped remote ticket severity/status; incomplete data rejected"
                )
            result.append(
                {
                    "id": str(row["Id"] if sf else row["incidentid"]),
                    "customer_id": cid,
                    "subject": row["Subject"] if sf else row["title"],
                    "severity": severity_map[severity],
                    "status": status_map[status],
                    "synthetic": False,
                }
            )
        return result

    def invoices(self, cid):
        if self.erp_mode == "mock":
            return erp_lookup(self.store, CustomerLookup(customer_id=cid))
        rows = self.adapters["sap"].invoices(self.external_id("ERP", cid), cid)
        as_of = os.getenv("REAL_AS_OF_DATE", "")
        if not as_of:
            raise IntegrationUnavailable(
                "REAL_AS_OF_DATE required; synthetic snapshot date is not assumed for real ERP"
            )
        date.fromisoformat(as_of)
        return {
            "invoices": rows,
            "orders": [],
            "indicators": financials(rows, as_of),
            "complete": True,
            "source": "sap",
            "synthetic": False,
            "limitations": ["Snapshot date is fixed; order normalization not enabled"],
        }

    def contracts(self, cid):
        if not self.fully_mock:
            return []  # Never join synthetic PDFs/contract records to a real account implicitly.
        return self.store.records("contracts", cid)

    def require_demo_documents(self):
        if not self.fully_mock:
            raise IntegrationUnavailable(
                "Real customer contract corpus not configured; synthetic contracts withheld"
            )

    def probe(self, name):
        if name not in self.adapters:
            raise KeyError("Unknown integration")
        status = self.statuses()[name]
        if status["mode"] == "mock":
            return {**status, "probe_executed": False, "reason": "Mock mode: no external request"}
        try:
            self.adapters[name].probe()
            return {**self.statuses()[name], "probe_executed": True}
        except IntegrationUnavailable:
            return {
                **self.statuses()[name],
                "probe_executed": False,
                "reason": "Not configured or read probe failed",
            }
