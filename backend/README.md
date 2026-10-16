# Agile Sales & Marketing — Backend

This is the independent backend foundation for **Agile Sales & Marketing**.

## Overview & Architecture

- **Product:** Agile Sales & Marketing
- **Status:** Early foundation phase.
- **Scope of Current Phase:** Clean backend setup and extracted, refactored HubSpot CRM integration layer.
- **Independence:** The existing Agile Receivables backend (`D:\Agile\agile-backend`) is **NOT** part of this application and remains untouched. No code from Agile Receivables business models (Leads, Proposals, Payments, etc.) is coupled to this project.
- **Version Control:** No Git repository is being initialized or committed at this stage.

## Integration Architecture: HubSpot CRM

HubSpot is treated strictly as an **external integration** service, not the core business model of this application. Future core models (Contacts, Companies, Campaigns, Outreach, Pipelines, Deals, Automations, Analytics) will maintain their own domain boundaries.

The integration layer is structured into modular services:
- **`HubSpotClient`** (`app/services/integrations/hubspot/client.py`):
  - Async HTTP client wrapping HubSpot CRM API v3 (`https://api.hubapi.com`).
  - Bearer token authentication via `HUBSPOT_ACCESS_TOKEN`.
  - Configurable timeouts (default 10s).
  - Explicit typed error mapping (`HubSpotAuthenticationError`, `HubSpotNotFoundError`, `HubSpotConflictError`, `HubSpotRateLimitError`, `HubSpotTimeoutError`, `HubSpotAPIError`).
  - Security guarantee: Access tokens are never logged or exposed in `__repr__` / log messages.
  - Lightweight connection test probe (`validate_credentials`).
- **`HubSpotContactService`** (`app/services/integrations/hubspot/contacts.py`):
  - Contact search by email (`POST /crm/v3/objects/contacts/search`).
  - Contact retrieval by ID with 404 recovery.
  - Contact creation and update.
  - Automatic 409 Conflict handling (resolves existing contact ID from error response or fallback email search and updates).
  - Uses only standard, verified HubSpot contact properties.
- **`HubSpotDealService`** (`app/services/integrations/hubspot/deals.py`):
  - Deal creation with standard properties (`dealname`, `amount`, `pipeline`, `dealstage`, `closedate`, `description`).
  - Duplicate prevention: if an existing deal ID is passed, performs an update instead of creating a duplicate deal.
  - Deal retrieval and update.
  - Stage update with amount and ISO UTC close date formatting.
- **`HubSpotAssociationService`** (`app/services/integrations/hubspot/associations.py`):
  - Association of Deals to Contacts (`PUT /crm/v3/objects/deals/{deal_id}/associations/contacts/{contact_id}/deal_to_contact`).
  - Clean association payload generator (`associationTypeId: 3`).
  - Association removal (`DELETE`).

## Directory Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── integrations/
│   │           ├── __init__.py
│   │           └── hubspot.py
│   └── services/
│       ├── __init__.py
│       └── integrations/
│           ├── __init__.py
│           └── hubspot/
│               ├── __init__.py
│               ├── client.py
│               ├── contacts.py
│               ├── deals.py
│               └── associations.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_hubspot_client.py
│   ├── test_hubspot_contacts.py
│   ├── test_hubspot_deals.py
│   ├── test_hubspot_associations.py
│   └── test_hubspot_api.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Configuration

Copy `.env.example` to `.env` and supply your HubSpot Private App Token or Personal Access Key:

```bash
cp .env.example .env
```

Environment variables:
- `HUBSPOT_ACCESS_TOKEN`: HubSpot Private App Token / Personal Access Key.
- `HUBSPOT_BASE_URL`: Base URL (default: `https://api.hubapi.com`).
- `HUBSPOT_TIMEOUT_SECONDS`: Request timeout in seconds (default: `10.0`).

## Running Locally

To run the FastAPI server:

```bash
uvicorn app.main:app --reload --port 8000
```

Access the interactive API documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Internal Connectivity Test API

- `GET /api/v1/integrations/hubspot/test`: Runs a lightweight read-only probe (`GET /crm/v3/owners?limit=1`) to verify API credentials without modifying any CRM data.
- `GET /api/v1/integrations/hubspot/contacts/{contact_id}`: Read-only probe for a specific contact.
- `GET /api/v1/integrations/hubspot/deals/{deal_id}`: Read-only probe for a specific deal.

## Running Tests

Run the unit test suite with pytest:

```bash
pytest
```
