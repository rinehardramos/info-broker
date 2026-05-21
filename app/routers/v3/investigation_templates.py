"""Built-in investigation templates for common use cases.

These are first-party question patterns shipped with the app. They appear in
GET /v3/investigation-templates and can be applied to populate the Research
page's query box. Distinct from /v3/templates which is per-user saved queries.

Each template has:
  - id: stable slug
  - name: display
  - description: one-line summary
  - icon: lucide-react icon name
  - category: kyc | due-diligence | market | finance | identity | general
  - query_template: parameterized query (uses {{var}} placeholders)
  - parameters: schema for the variables the user fills in
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from app.routers.v3.auth import get_current_user

router = APIRouter(prefix="/v3", tags=["v3-investigation-templates"])


INVESTIGATION_TEMPLATES: list[dict] = [
    {
        "id": "kyc-individual",
        "name": "KYC — Individual",
        "description": "Verify identity, employment, sanctions, PEP status, and adverse media for one person.",
        "icon": "UserSearch",
        "category": "kyc",
        "query_template": (
            "KYC due diligence on {{full_name}}. Verify: legal identity and aliases; "
            "current employment and role at {{employer}}; nationality and current location; "
            "sanctions/OFAC/PEP status; adverse media (fraud, lawsuits, regulatory actions) "
            "in the last 5 years. Cite primary sources where possible."
        ),
        "parameters": [
            {"name": "full_name", "label": "Full name", "type": "text", "required": True,
             "placeholder": "Jane Doe"},
            {"name": "employer", "label": "Employer / company (optional)", "type": "text",
             "placeholder": "Acme Corp"},
        ],
    },
    {
        "id": "kyb-company",
        "name": "KYB — Company",
        "description": "Verify a company's legal registration, ownership, financials, sanctions, and reputation.",
        "icon": "Building2",
        "category": "kyc",
        "query_template": (
            "KYB due diligence on {{company_name}} ({{jurisdiction}}). Verify: legal "
            "incorporation and registration status; ultimate beneficial owners and "
            "shareholders; current officers and directors; recent financial filings; "
            "any sanctions, regulatory actions, or adverse media. Use SEC EDGAR / "
            "OpenCorporates / local registry where applicable."
        ),
        "parameters": [
            {"name": "company_name", "label": "Company name", "type": "text", "required": True,
             "placeholder": "Anthropic, PBC"},
            {"name": "jurisdiction", "label": "Jurisdiction (country/state)", "type": "text",
             "placeholder": "Delaware, USA"},
        ],
    },
    {
        "id": "vc-due-diligence",
        "name": "VC Pre-Investment Due Diligence",
        "description": "Comprehensive pre-investment review of a target company — team, market, traction, risks.",
        "icon": "TrendingUp",
        "category": "due-diligence",
        "query_template": (
            "Pre-investment due diligence on {{company_name}}. Profile: founding team "
            "and prior exits; current funding round size and lead investor; revenue / "
            "ARR / growth rate (latest reporting); main competitors and market position; "
            "key risks (technical, regulatory, market). Cite primary sources — investor "
            "decks, S-1/20-F if applicable, founder interviews, press releases."
        ),
        "parameters": [
            {"name": "company_name", "label": "Target company", "type": "text", "required": True,
             "placeholder": "Acme Pay"},
        ],
    },
    {
        "id": "competitor-mapping",
        "name": "Competitor Landscape",
        "description": "Map direct + adjacent competitors of a company with positioning, traction, and recent moves.",
        "icon": "Network",
        "category": "market",
        "query_template": (
            "Map the competitive landscape for {{company_name}} in the {{market_segment}} "
            "market. For each competitor: name, founding year, funding stage, employee "
            "headcount, key product differentiator, recent strategic moves in the last "
            "12 months. Include both direct competitors and adjacent players that could "
            "expand into this space."
        ),
        "parameters": [
            {"name": "company_name", "label": "Target company", "type": "text", "required": True,
             "placeholder": "Acme Pay"},
            {"name": "market_segment", "label": "Market segment", "type": "text", "required": True,
             "placeholder": "SEA cross-border payments"},
        ],
    },
    {
        "id": "financial-health",
        "name": "Public Company Financial Snapshot",
        "description": "Latest revenue, profit/loss, cash position, and trend for a publicly-traded company.",
        "icon": "BarChart3",
        "category": "finance",
        "query_template": (
            "Provide a financial snapshot of {{ticker}} ({{exchange}}) for {{fiscal_year}}. "
            "Include: revenue, gross margin, GAAP net income/loss, adjusted EBITDA, "
            "operating cash flow, free cash flow, cash + equivalents, total debt, and "
            "year-over-year growth. Lean on the company's own 10-K / 20-F / 6-K filings "
            "on SEC EDGAR and the investor-relations site."
        ),
        "parameters": [
            {"name": "ticker", "label": "Ticker", "type": "text", "required": True,
             "placeholder": "GRAB"},
            {"name": "exchange", "label": "Exchange", "type": "text", "required": True,
             "placeholder": "NASDAQ"},
            {"name": "fiscal_year", "label": "Fiscal year", "type": "text", "required": True,
             "placeholder": "FY2024"},
        ],
    },
    {
        "id": "identity-disambiguation",
        "name": "Identity Disambiguation",
        "description": "Resolve which of several people / companies sharing a name is the intended subject.",
        "icon": "Users",
        "category": "identity",
        "query_template": (
            "There are multiple distinct entities named {{name}}. Identify and "
            "differentiate them — at minimum, the {{count}} most prominent — by: "
            "primary domain, industry, headquarters city, and one short biographical "
            "hook each. The user's intended subject is described as: \"{{hint}}\"."
        ),
        "parameters": [
            {"name": "name", "label": "Ambiguous name", "type": "text", "required": True,
             "placeholder": "Acme"},
            {"name": "count", "label": "How many?", "type": "number", "required": True,
             "placeholder": "3"},
            {"name": "hint", "label": "Hint about the intended subject", "type": "text",
             "placeholder": "Singapore-based fintech founded ~2017"},
        ],
    },
]


@router.get("/investigation-templates")
def list_investigation_templates(user: dict = Depends(get_current_user)) -> list[dict]:
    """Return the built-in investigation templates available to the user.

    Non-admin users see only templates visible at their effective scope
    (per #107 visibility settings). Admins always see the full catalog.
    """
    if user.get("is_admin") or user.get("role") == "admin":
        return INVESTIGATION_TEMPLATES

    from app.routers.v3.visibility import filter_visible
    org_id = str(user["org_id"]) if user.get("org_id") else None
    return filter_visible("template", INVESTIGATION_TEMPLATES, org_id)


@router.get("/investigation-templates/{template_id}")
def get_investigation_template(
    template_id: str, user: dict = Depends(get_current_user),
) -> dict:
    """Return a single template by id."""
    for tpl in INVESTIGATION_TEMPLATES:
        if tpl["id"] == template_id:
            return tpl
    raise HTTPException(status_code=404, detail="template not found")


def render_query(template_id: str, params: dict[str, str]) -> str:
    """Substitute {{var}} placeholders in a template's query_template.

    Empty / missing params render as "(not specified)" so the brain knows
    the variable was intentionally omitted rather than the literal placeholder
    remaining in the text. Pure function, importable for tests + the UI's
    server-side query rendering path.
    """
    for tpl in INVESTIGATION_TEMPLATES:
        if tpl["id"] != template_id:
            continue
        rendered = tpl["query_template"]
        for p in tpl["parameters"]:
            key = p["name"]
            val = (params.get(key) or "").strip()
            if not val:
                val = "(not specified)"
            rendered = rendered.replace("{{" + key + "}}", val)
        return rendered
    raise KeyError(f"unknown template id: {template_id}")
