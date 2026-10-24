from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Query(StrictModel):
    message: str = Field(min_length=3, max_length=2000)
    customer_id: str | None = Field(default=None, pattern=r"^C\d{3}$")
    prepare_actions: bool = False
    execution_mode: Literal["auto", "baseline", "agent", "hybrid"] = "auto"


class CustomerLookup(StrictModel):
    customer_id: str = Field(pattern=r"^C\d{3}$")


class Search(StrictModel):
    query: str = Field(min_length=2, max_length=500)
    customer_id: str | None = Field(default=None, pattern=r"^C\d{3}$")
    limit: int = Field(default=4, ge=1, le=10)
    retrieval_mode: Literal["lexical", "hybrid"] = "lexical"


class CatalogueLookup(StrictModel):
    search: str = Field(default="", max_length=100)


class ContractSearch(Search):
    """Agent document reads always require a customer; general API search remains unchanged."""

    customer_id: str = Field(pattern=r"^C\d{3}$")


class FactSelection(StrictModel):
    fact_id: str = Field(max_length=200)
    customer_id: str = Field(pattern=r"^C\d{3}$")
    text: str = Field(min_length=1, max_length=1800)


class Recommendation(StrictModel):
    customer_id: str = Field(pattern=r"^C\d{3}$")
    action: Literal["payment_plan", "support_escalation", "renewal_review", "legal_review", "verify_data"]
    based_on: list[str] = Field(min_length=1, max_length=10)
    priority: Literal["normal", "urgent"] = "normal"


class GroundedDraft(StrictModel):
    analysis: Literal["lookup", "risk"] = "lookup"
    claims: list[FactSelection] = Field(default_factory=list, max_length=60)
    recommendations: list[Recommendation] = Field(default_factory=list, max_length=30)
    abstain: bool = False


class Route(StrictModel):
    intent: Literal["risk", "crm", "erp", "contracts", "help"]
    customer_id: str | None = Field(default=None, pattern=r"^C\d{3}$")
    reason: str = Field(max_length=500)


class Decision(StrictModel):
    approved: StrictBool
    actor: str = Field(min_length=2, max_length=80, pattern=r"^[\w .@-]+$")
    note: str = Field(default="", max_length=500)


class Interpretation(StrictModel):
    interpretation: str = Field(min_length=1, max_length=1200)
    evidence_ids: list[str] = Field(max_length=12)
