# Backend Technical Guide & Architecture

**Platform:** Agile Sales & Marketing  
**Backend Location:** `D:\Agile-Sales-Marketing\backend`  
**Audit Date:** October 2026  
**Auditor Roles:** Senior Backend Architect, Python Specialist  

---

## 1. Backend Framework & Application Entrypoint

* **Framework:** FastAPI `0.115+` with Uvicorn server (`uvicorn[standard]>=0.30.0`).
* **Python Runtime:** Python 3.11 / 3.13.
* **Entrypoint:** `backend/app/main.py`.

### Application Bootstrap
In `main.py`, the FastAPI application initializes with metadata and mounts:
1. Standard logging configuration with debug switching based on `settings.DEBUG`.
2. Cross-Origin Resource Sharing (CORS) middleware configured to allow frontend communication.
3. Master API router mounted at `settings.API_V1_STR` (`/api/v1`).
4. Root status probe (`GET /`) and comprehensive application health check (`GET /health`).

```python
# main.py excerpt
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API for Agile Sales & Marketing platform.",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.API_V1_STR)
```

---

## 2. API Routing Structure (`backend/app/api/v1`)

The router aggregation in `backend/app/api/v1/__init__.py` cleanly composes 17 modular routers:

| Router Module | Mount / Prefix | Primary Responsibilities |
| :--- | :--- | :--- |
| `auth.py` | `/auth` | User registration, login, token refresh, and user profile (`/me`). |
| `leads.py` | `/leads` | Lead discovery, CRUD, temperature filtering, and lead deletion. |
| `campaigns.py` | `/campaigns` | Campaign CRUD, contact enrollment, contact removal, and campaign deletion. |
| `campaign_steps.py`| `/campaigns/{id}/steps`| Sequence steps, delays, subject/body templates, and contact preview. |
| `campaign_execution.py`| `/campaigns/{id}/execute` | Read-only execution dry-run and campaign outreach initialization. |
| `outreach.py` | `/outreach` | Outreach lifecycle management, delivery triggering, retry, and cancellation. |
| `tracking.py` | `/tracking` | Email open pixel (`/pixel/{id}`) and click redirect tracking (`/click/{id}`). |
| `voice_webhook.py` | `/voice/webhook` | Retell AI voice call webhook handler and automated follow-ups. |
| `integrations/hubspot.py` | `/integrations/hubspot` | Read-only HubSpot CRM synchronization and audit status. |
| `companies.py` | `/companies` | B2B business account CRUD. |
| `contacts.py` | `/contacts` | CRM decision-maker contact CRUD and deduplication. |
| `pipeline.py` | `/pipelines` | Sales pipeline workflow stages and deal boards. |
| `deals.py` | `/deals` | Commercial deal tracking, stage progression, and probability. |
| `icp.py` | `/icp` | Ideal Customer Profile definitions and scoring criteria. |
| `lead_research.py` | `/lead-research` | Deep company research and firmographic enrichment. |
| `routing_rules.py` | `/routing-rules` | Automated lead assignment rules based on scoring/geography. |
| `analytics.py` | `/analytics` | Aggregated revenue, outreach, and call performance metrics. |

---

## 3. Dependency Injection & Multi-Tenant Authority (`deps.py`)

FastAPI's dependency injection system guarantees that database sessions and authenticated tenant contexts are strictly resolved before request handlers execute:

1. **`get_db()` (`core/database.py`):**
   * Yields a scoped SQLAlchemy database session and guarantees closure in a `finally` block.
2. **`get_current_user()` (`api/deps.py`):**
   * Parses the `Authorization: Bearer <token>` header using `HTTPBearer`.
   * Decodes and validates the JWT token against `SECRET_KEY` and `JWT_ALGORITHM`.
   * Verifies token expiration (`ExpiredTokenError`) and user existence in the database.
3. **`get_current_organization()` (`api/deps.py`):**
   * Derives tenant authority directly from `current_user.organization_id` or the verified token claims.
   * Eliminates cross-tenant tampering because clients cannot supply an arbitrary `organization_id` in query parameters or request payloads.

---

## 4. Service Layer Design & Business Logic

Business rules and database transactions are encapsulated in `backend/app/services`, keeping API route handlers lean:

* **Transactional Atomicity (`db.begin_nested()`):**
  * Critical multi-step workflows (e.g., campaign execution and outreach dispatch) use savepoints and nested transactions so individual contact failures roll back cleanly without aborting the entire batch.
* **Domain Exceptions:**
  * Services define clean domain exceptions (e.g. `SuppressedRecipientError`, `UnresolvedTemplatePlaceholderError`, `AlreadySentError`).
  * API route handlers catch these exceptions and translate them into standard HTTP status codes (e.g., 400 Bad Request, 404 Not Found, 409 Conflict).

---

## 5. Template Rendering & Placeholder Validation Engine

Located in `backend/app/services/campaign_steps/template_renderer.py`:

* **Supported Placeholder Tokens:**
  * Contact tokens: `{{contact.first_name}}`, `{{contact.last_name}}`, `{{contact.email}}`, `{{contact.job_title}}`.
  * Company tokens: `{{company.name}}`, `{{company.domain}}`, `{{company.industry}}`.
  * Sender tokens: `{{sender.name}}`, `{{sender.email}}`.
* **Fail-Safe Placeholder Detection:**
  * `find_unresolved_placeholders(text)` uses regex `\{\{([a-zA-Z0-9_.]+)\}\}` to scan rendered text.
  * If any placeholder remains unreplaced (e.g. a contact lacks a `job_title` and no fallback is defined), outreach delivery is **strictly blocked** to preserve professional brand reputation.

---

## 6. Background Processing & Current Limitations

* **Current Architecture:**
  * Campaign outreach creation and single-email dispatch execute synchronously via FastAPI endpoint requests.
  * Long-running operations (like HubSpot CRM synchronization) run asynchronously using Python `asyncio` inside the ASGI event loop.
* **Architectural Limitation (Technical Debt):**
  * There is currently no external task queue (such as Celery, Temporal, or RQ) or background scheduling daemon (such as APScheduler or cron).
  * Consequently, sequence step delays (e.g., "Wait 2 days before sending Step 2") cannot fire automatically unless an external scheduler invokes the execution endpoint.
