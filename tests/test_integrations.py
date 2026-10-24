import json
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from copilot.integrations import (
    Dynamics365Connector,
    FoundryConnector,
    IntegrationHub,
    IntegrationUnavailable,
    SAPConnector,
    SalesforceConnector,
    cents,
)


def configure(monkeypatch, prefix):
    monkeypatch.setenv(prefix + "_ENDPOINT", "https://tenant.example.invalid")
    monkeypatch.setenv(prefix + "_ACCESS_TOKEN", "fixture-token")


def test_mock_status_makes_no_external_request(engine):
    for adapter in engine.integrations.adapters.values():
        adapter.transport = httpx.MockTransport(
            lambda request: pytest.fail("Mock mode contacted an external adapter")
        )
    assert all(
        s["status"] == "mock" and not s["live_verified"] for s in engine.integrations.statuses().values()
    )
    assert engine.integrations.probe("salesforce")["probe_executed"] is False
    assert len(engine.integrations.customers()) == 30


def test_real_unconfigured_fails_closed_without_synthetic_substitution(engine, monkeypatch):
    monkeypatch.setenv("CRM_MODE", "real")
    hub = IntegrationHub(engine.store)
    with pytest.raises(IntegrationUnavailable):
        hub.customers()
    assert hub.statuses()["salesforce"]["status"] == "unconfigured"
    with pytest.raises(IntegrationUnavailable):
        hub.require_demo_documents()
    assert hub.contracts("C001") == []


def test_salesforce_request_and_status_are_not_falsely_verified(monkeypatch):
    configure(monkeypatch, "SALESFORCE")
    adapter = SalesforceConnector()
    assert adapter.status()["status"] == "configured_unverified"
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"Id": "001000000000001AAA", "Name": "Remote account fixture"})

    adapter.transport = httpx.MockTransport(handle)
    assert adapter.account("001000000000001AAA")["Name"] == "Remote account fixture"
    assert seen[0].method == "GET" and "/sobjects/Account/" in seen[0].url.path
    assert adapter.status()["status"] == "configured_unverified" and not adapter.status()["live_verified"]
    with pytest.raises(ValueError):
        adapter.account("001';DROP TABLE Account")


def test_dynamics_read_contract(monkeypatch):
    configure(monkeypatch, "DYNAMICS365")
    adapter = Dynamics365Connector()
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            200, json={"accountid": "00000000-0000-0000-0000-000000000001", "name": "Dynamics fixture"}
        )

    adapter.transport = httpx.MockTransport(handle)
    assert adapter.account("00000000-0000-0000-0000-000000000001")["name"] == "Dynamics fixture"
    assert seen[0].url.path.startswith("/api/data/v9.2/accounts(")
    with pytest.raises(ValueError):
        adapter.account("../accounts")


def test_wrong_customer_response_rejected(monkeypatch):
    configure(monkeypatch, "SALESFORCE")
    adapter = SalesforceConnector()
    adapter.transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"Id": "001000000000002AAA", "Name": "Wrong account"})
    )
    with pytest.raises(IntegrationUnavailable):
        adapter.account("001000000000001AAA")


def test_real_write_adapters_are_not_exposed(engine):
    for adapter in engine.integrations.adapters.values():
        assert not adapter.status()["remote_writes_supported"]
        assert not hasattr(adapter, "create_task")


def test_cross_origin_pagination_and_redirect_rejected(monkeypatch):
    configure(monkeypatch, "DYNAMICS365")
    adapter = Dynamics365Connector()
    adapter.transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"value": [], "@odata.nextLink": "https://attacker.invalid/steal"}
        )
    )
    with pytest.raises(IntegrationUnavailable):
        adapter.pages("/api/data/v9.2/accounts")
    adapter.transport = httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"Location": "https://attacker.invalid"})
    )
    with pytest.raises(IntegrationUnavailable):
        adapter.account("00000000-0000-0000-0000-000000000001")


def test_sap_explicit_field_mapping_and_exact_cents(monkeypatch):
    configure(monkeypatch, "SAP")
    monkeypatch.setenv("SAP_OPEN_ITEMS_PATH", "/odata/OpenItems")
    monkeypatch.setenv(
        "SAP_INVOICE_FIELD_MAP",
        json.dumps(
            {
                "id": "Invoice",
                "customer": "Customer",
                "amount": "Amount",
                "paid": "Paid",
                "currency": "Currency",
                "due_date": "Due",
            }
        ),
    )
    adapter = SAPConnector()
    rows = [
        {
            "Invoice": "R-1",
            "Customer": "1001",
            "Amount": "100.10",
            "Paid": "33.33",
            "Currency": "EUR",
            "Due": "2026-10-01",
        }
    ]
    adapter.transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"d": {"results": rows}})
    )
    invoice = adapter.invoices("1001", "C001")[0]
    assert invoice["amount_cents"] - invoice["paid_cents"] == 6677
    assert not invoice["synthetic"] and invoice["due_date"] == "2026-10-01"
    rows[0]["Currency"] = "USD"
    with pytest.raises(IntegrationUnavailable):
        adapter.invoices("1001", "C001")


def test_sap_requires_mapping(monkeypatch):
    configure(monkeypatch, "SAP")
    monkeypatch.delenv("SAP_OPEN_ITEMS_PATH", raising=False)
    with pytest.raises(IntegrationUnavailable):
        SAPConnector().invoices("1001", "C001")


@pytest.mark.parametrize("value", ["NaN", "-1", "0.001", "Infinity"])
def test_invalid_money_rejected(value):
    with pytest.raises(ValueError):
        cents(value)


def test_decimal_money_is_exact():
    assert cents(Decimal("100.10")) == 10010


def test_foundry_is_unconfigured_and_model_probe_has_no_inference_claim(monkeypatch):
    monkeypatch.delenv("AZURE_FOUNDRY_ENDPOINT", raising=False)
    adapter = FoundryConnector()
    assert adapter.status()["status"] == "unconfigured"
    with pytest.raises(IntegrationUnavailable):
        adapter.probe()
    adapter.endpoint = "https://resource.example.invalid/openai/v1"
    adapter.token = "fixture-api-key"
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "fixture-deployment"}]})

    adapter.transport = httpx.MockTransport(handle)
    assert adapter.probe()["data"]
    assert seen[0].url.path == "/openai/v1/models"
    assert not adapter.status()["live_verified"]


def test_real_api_returns_503_instead_of_mock_customers(tmp_path, monkeypatch):
    from copilot.api import create_app

    monkeypatch.setenv("CRM_MODE", "real")
    monkeypatch.delenv("CRM_ID_MAP_PATH", raising=False)
    with TestClient(create_app(tmp_path)) as client:
        result = client.get("/customers")
        assert result.status_code == 503 and result.json()["mock_substitution"] is False
        assert client.get("/integrations").json()["salesforce"]["status"] == "unconfigured"


def test_normalized_real_account_and_explicit_ticket_mapping(engine, monkeypatch, tmp_path):
    configure(monkeypatch, "SALESFORCE")
    monkeypatch.setenv("CRM_MODE", "real")
    mapping = tmp_path / "id-map.json"
    mapping.write_text(json.dumps({"C001": "001000000000001AAA"}))
    monkeypatch.setenv("CRM_ID_MAP_PATH", str(mapping))
    monkeypatch.setenv("CRM_TICKET_SEVERITY_MAP", '{"High":"critical"}')
    monkeypatch.setenv("CRM_TICKET_STATUS_MAP", '{"New":"open"}')
    hub = IntegrationHub(engine.store)

    def handle(request):
        if "/sobjects/" in request.url.path:
            return httpx.Response(200, json={"Name": "Actual response fixture", "Id": "001000000000001AAA"})
        return httpx.Response(
            200,
            json={
                "records": [
                    {"Id": "case-1", "Subject": "Incident fixture", "Priority": "High", "Status": "New"}
                ],
                "done": True,
            },
        )

    hub.adapters["salesforce"].transport = httpx.MockTransport(handle)
    assert hub.customers()[0]["name"] == "Actual response fixture"
    assert hub.tickets("C001")[0]["severity"] == "critical"
    assert not hub.customers()[0]["synthetic"]


def test_external_credentials_and_endpoints_are_blank_in_example():
    from dotenv import dotenv_values
    from copilot.config import ROOT

    example = dotenv_values(ROOT / ".env.example")
    for key in [
        "SALESFORCE_ENDPOINT",
        "SALESFORCE_ACCESS_TOKEN",
        "DYNAMICS365_ENDPOINT",
        "DYNAMICS365_ACCESS_TOKEN",
        "SAP_ENDPOINT",
        "SAP_ACCESS_TOKEN",
        "AZURE_FOUNDRY_ENDPOINT",
        "AZURE_FOUNDRY_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "LLM_API_KEY",
        "LLM_BASE_URL",
    ]:
        assert not example[key]
