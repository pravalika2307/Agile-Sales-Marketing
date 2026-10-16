# System Architecture & Technical Topology

**Platform:** Agile Sales & Marketing  
**Audit Date:** October 2026  
**Auditor Roles:** Senior Software Architect, Full-Stack Engineer  
**Document Purpose:** Architectural blueprint detailing component topology, request lifecycle, service boundaries, data isolation, and integration touchpoints.

---

## 1. High-Level Architecture Diagram

The Agile Sales & Marketing platform implements a decoupled, modern multi-tier architecture consisting of a Next.js App Router frontend, a FastAPI asynchronous Python backend, a relational PostgreSQL database with Alembic schema management, and multiple external service integrations.

```mermaid
graph TB
    subgraph ClientLayer ["Client Presentation Layer (Browser)"]
        UI["Next.js 16 / React 19 UI<br/>(Tailwind CSS, Lucide, AppShell)"]
    end

    subgraph FrontendServer ["Next.js App Router (BFF Layer)"]
        NextAPI["Next.js Route Handlers<br/>(/api/leads, /api/campaigns, etc.)"]
    end

    subgraph BackendGateway ["FastAPI Application Gateway (:8000)"]
        CORS["CORS Middleware"]
        Router["APIRouter (/api/v1)"]
        Deps["Dependency Injection<br/>(deps.py: get_current_user, get_current_org)"]
    end

    subgraph ServiceLayer ["Domain Services Layer"]
        LeadSvc["Lead Generation & ICP Scoring"]
        CampSvc["Campaign & Sequence Service"]
        OutreachSvc["Outreach & Delivery Engine"]
        VoiceSvc["Voice Follow-Up Service"]
        HubSpotSvc["HubSpot Sync Engine"]
        AnalyticsSvc["Analytics Aggregator"]
    end

    subgraph PersistenceLayer ["Persistence & Database Layer"]
        Postgres[(PostgreSQL 16 Database)]
        Alembic["Alembic Migrations (15 Versions)"]
    end

    subgraph ExternalProviders ["External Service Integrations"]
        SES["AWS SES (Email Provider)"]
        Retell["Retell AI (Voice Telephony)"]
        HubSpotAPI["HubSpot CRM v3 (Read-Only)"]
        Resend["Resend API (Alternative Provider)"]
    end

    UI -->|"HTTP Fetch (JSON)"| NextAPI
    NextAPI -->|"Proxy HTTP (Bearer / Default Org)"| CORS
    CORS --> Router
    Router --> Deps
    Deps --> ServiceLayer

    LeadSvc -->|"SQLAlchemy 2.0 ORM"| Postgres
    CampSvc -->|"SQLAlchemy 2.0 ORM"| Postgres
    OutreachSvc -->|"SQLAlchemy 2.0 ORM"| Postgres
    VoiceSvc -->|"SQLAlchemy 2.0 ORM"| Postgres
    HubSpotSvc -->|"SQLAlchemy 2.0 ORM"| Postgres
    AnalyticsSvc -->|"SQLAlchemy 2.0 ORM"| Postgres

    OutreachSvc -->|"boto3 (Raw SES API)"| SES
    OutreachSvc -->|"httpx REST"| Resend
    VoiceSvc <-->|"Webhook HMAC-SHA256"| Retell
    HubSpotSvc -->|"httpx REST (Cursor Paging)"| HubSpotAPI
    Alembic -.->|"Schema Evolution"| Postgres
```

---

## 2. Component Responsibilities

### 2.1. Client Presentation Layer (Next.js 16 / React 19)
* **Location:** `D:\Agile-Sales-Marketing\frontend`
* **Responsibilities:**
  * Render interactive dashboards, lead catalogs, campaign workflow sequence builders, and detail drawers.
  * Execute client-side form validation, search debouncing, and pagination controls.
  * Provide defensive confirmation modals with loading spinners for destructive operations (e.g. Lead Deletion, Campaign Deletion, Contact Removal).
  * Render live template preview by switching contact records dynamically.

### 2.2. Frontend Proxy / BFF Layer (`frontend/src/app/api`)
* **Responsibilities:**
  * Route handlers proxy client calls to the backend (`http://localhost:8000/api/v1`).
  * Handles Next.js edge caching and request forwarding.
  * Standardizes JSON error formatting for the UI.

### 2.3. Backend Gateway & API Layer (FastAPI)
* **Location:** `D:\Agile-Sales-Marketing\backend\app\api\v1`
* **Entrypoint:** `backend/app/main.py`
* **Responsibilities:**
  * CORS middleware configuration allowing local frontend communication.
  * URL routing, HTTP parameter parsing, and Pydantic v2 schema validation.
  * OpenAPI interactive documentation (`/docs`, `/redoc`).
  * Authentication enforcement and tenant organization resolution via `deps.py`.

### 2.4. Domain Services Layer (`backend/app/services`)
* **Responsibilities:**
  * Encapsulate core business rules, transaction boundaries, and domain exceptions.
  * **Lead Service:** Manages lead CRUD, auto-associates matching CRM Contacts, and executes ICP qualification evaluation.
  * **Campaign Service:** Manages campaigns, sequence steps, contact enrollments, and safe dissociation of historical outreach upon deletion.
  * **Outreach Service:** Manages the outreach state machine (`draft` -> `sending` -> `sent`/`failed`), fail-closed recipient suppression checks, unresolved template token validation, and email dispatch.
  * **Voice Follow-up Service:** Validates Retell webhook HMAC-SHA256 signatures, extracts structured variables, enforces idempotency, and schedules automated email follow-ups.
  * **HubSpot Service:** Asynchronously fetches contacts, companies, and deals from HubSpot API v3, mapping external IDs and logging sync runs.

### 2.5. Persistence Layer (PostgreSQL & SQLAlchemy 2.0)
* **ORM:** Modern mapped columns (`Mapped[T] = mapped_column(...)`) with type safety.
* **Driver:** `psycopg` (v3.2 binary driver).
* **Migrations:** Managed via Alembic (`backend/alembic/versions`), tracking 15 historical schema revisions.

---

## 3. Communication Patterns & Request Lifecycle

A typical data mutation follows this end-to-end execution path:

```mermaid
sequenceDiagram
    autonumber
    actor User as User Browser
    participant FE as Next.js UI Component
    participant BFF as Next.js API Route (/api/...)
    participant FastAPI as FastAPI Router (/api/v1/...)
    participant Deps as Auth & Tenant Dependency (deps.py)
    participant Svc as Domain Service Layer
    participant DB as PostgreSQL Database
    participant Ext as External Provider (AWS SES)

    User->>FE: Clicks "Send Outreach"
    FE->>BFF: POST /api/outreach/{id}/send
    BFF->>FastAPI: POST /api/v1/outreach/{id}/send (Forward)
    FastAPI->>Deps: Resolve get_current_user & get_current_organization
    Deps-->>FastAPI: Organization context (org_id)
    FastAPI->>Svc: send_outreach(db, org_id, outreach_id)
    Svc->>DB: Query Outreach (verify org_id & lock row)
    Svc->>Svc: Suppression Check (fail-closed if opted_out)
    Svc->>Svc: Template Check (block unresolved tokens)
    Svc->>DB: Update status='sending', write OutreachEvent
    Svc->>Ext: Deliver email via boto3 SES client
    Ext-->>Svc: Provider accepted (MessageId)
    Svc->>DB: Update status='sent', set provider_message_id, write OutreachEvent
    DB-->>Svc: Commit transaction
    Svc-->>FastAPI: Outreach domain model
    FastAPI-->>BFF: 200 OK (OutreachResponse JSON)
    BFF-->>FE: 200 OK
    FE->>User: Display success banner & refresh table
```

---

## 4. Multi-Tenant Isolation Strategy

The platform implements **Shared Database, Shared Schema with Logical Row-Level Tenant Isolation**:

1. **Foreign Key Enforcement:** Every tenant-owned table (`contacts`, `companies`, `campaigns`, `campaign_steps`, `outreach`, `leads`, `call_records`, `hubspot_sync_runs`) has a non-nullable `organization_id` foreign key referencing `organizations(id)` with `ondelete="CASCADE"`.
2. **Authority Resolution:** The current organization is never accepted as a raw request body parameter from the client. It is derived in `get_current_organization()` (`backend/app/api/deps.py`) strictly from the authenticated JWT token or user identity.
3. **Cross-Tenant Parameter Tampering Defense:** All database queries in service layers include `filter(Model.organization_id == current_org.id)`. Any attempt by Tenant A to query or mutate a record belonging to Tenant B returns an immediate HTTP 404 (Not Found).
