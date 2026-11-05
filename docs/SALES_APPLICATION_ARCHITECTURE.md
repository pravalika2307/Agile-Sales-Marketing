# Agile Sales Application Architecture & Technical Specification

> **Audience:** Lakshay & Agile Engineering Team  
> **Repository:** `D:\Agile-Sales-Marketing`  
> **Scope:** Sales Application Only (Excludes Marketing-specific modules)  
> **Status:** Production-Hardened Architecture & Verified Implementation  
> **Current Database Revision:** `a1b2c3d4e5f7` (PostgreSQL 16)  
> **Last Updated:** November 2026  

---

## Table of Contents

1. [Executive Overview](#1-executive-overview)
2. [Sales Application Feature Inventory](#2-sales-application-feature-inventory)
3. [Technology Stack](#3-technology-stack)
4. [High-Level System Architecture](#4-high-level-system-architecture)
5. [Frontend Architecture](#5-frontend-architecture)
6. [Backend Architecture](#6-backend-architecture)
7. [Database Architecture](#7-database-architecture)
8. [Sales Workflows – End to End](#8-sales-workflows--end-to-end)
9. [External Integrations](#9-external-integrations)
10. [API Documentation](#10-api-documentation)
11. [Authentication, Authorization and Security](#11-authentication-authorization-and-security)
12. [Background Jobs and Asynchronous Processing](#12-background-jobs-and-asynchronous-processing)
13. [Testing and Quality Assurance](#13-testing-and-quality-assurance)
14. [Local Development Setup](#14-local-development-setup)
15. [Deployment and Infrastructure](#15-deployment-and-infrastructure)
16. [Current Limitations and Technical Debt](#16-current-limitations-and-technical-debt)
17. [Future Architecture Improvements](#17-future-architecture-improvements)
18. [Glossary](#18-glossary)
19. [Important File and Directory Reference](#19-important-file-and-directory-reference)

---

## 1. Executive Overview

### 1.1 What Agile Sales Is
The **Agile Sales** application is an enterprise-grade B2B sales acceleration, CRM, and multi-channel outreach execution platform. It is engineered to enable Sales Development Representatives (SDRs), Account Executives (AEs), and sales managers to discover high-fit prospects, manage qualified leads, execute automated multi-channel sales cadences (Cold Email, AI Voice SDR calls, 1-on-1 SMS, and assisted LinkedIn outreach), track pipeline opportunities, reconcile inbound support emails, and synchronize seamlessly with HubSpot CRM.

The repository `D:\Agile-Sales-Marketing` houses both Sales and Marketing capabilities within a unified codebase. However, this architecture specification focuses strictly on the **Sales** side of the platform.

### 1.2 Business Problem Solved
B2B outbound sales teams typically struggle with fragmented tooling:
- Prospecting data is separated from execution cadences.
- Voice calls require manual dialing and manual CRM logging.
- Cold email sequences fail to pause automatically when prospects reply or request callbacks.
- Inbound replies sent to support mailboxes get lost or fail to associate with open deals.
- Customer CRM data in HubSpot drifts out of sync with outbound engagement tools.
- Multi-channel steps (Email + AI Voice + SMS) often race or double-execute due to synchronous request timeouts.

Agile Sales resolves these problems by providing:
1. **Unified CRM & Pipeline Tracking:** Leads, Contacts, Companies, and Deals with strict tenant isolation.
2. **Automated AI Voice Calling:** Real-time conversational AI voice agents powered by Retell AI that qualify prospects, handle objections, capture interest variables, and trigger deterministic email follow-ups.
3. **Durable Asynchronous Step Execution:** A PostgreSQL-backed job queue utilizing `SELECT ... FOR UPDATE SKIP LOCKED` and lease-fencing tokens to execute multi-step cadences reliably in the background without single-HTTP-request timeouts.
4. **Automated Inbound Support Mailbox Reconciliation:** Automatic synchronization with Microsoft 365 shared mailboxes (`support@agilereceivables.com`) to match inbound responses directly with CRM contacts and open leads.
5. **Fail-Closed Safety Controls:** Strict segregation between operational production data (`agile-sales-marketing-org`) and exploratory testing (`agile-qa-sandbox-org`), combined with compile-time and runtime guards preventing accidental real-world email or call dispatch during testing.

### 1.3 Target Users
- **Sales Development Representatives (SDRs):** Prospect discovery, list segmentation, multi-channel cadence enrollment, AI voice call follow-ups, and inbound response handling.
- **Account Executives (AEs):** Deal qualification, stage progression, pipeline forecasting, contact engagement history inspection, and meeting booking.
- **Sales Leadership & Operations:** Channel entitlement governance, capacity allocation, lead routing rule configuration, and conversion analytics.
- **Platform Administrators:** Tenant provisioning, channel unlocks (SMS/Voice/Physical Mail), and global audit review.

### 1.4 How Major Components Work Together
```
+----------------------------------------------------------------------------------------------------+
|                                    Next.js 16 App Router (React 19)                                 |
|   /sales Dashboard  |  /sales/find-leads  |  /sales/leads  |  /sales/pipeline  |  /inbox  | ...    |
+----------------------------------------------------------------------------------------------------+
                                                 |
                                     (BFF HTTP Proxy via /api/*)
                                                 v
+----------------------------------------------------------------------------------------------------+
|                                      FastAPI 0.115 Backend API                                     |
|  - Dependency Injection (get_current_user, get_current_organization)                               |
|  - API v1 Routers (leads, contacts, deals, pipeline, outreach, voice, sms, hubspot, graph)         |
|  - Lifespan Background Tasks (CampaignSchedulerService & Microsoft Graph Auto-Sync)                |
+----------------------------------------------------------------------------------------------------+
            |                                           |                                  |
            v                                           v                                  v
+-------------------------+               +----------------------------+        +--------------------+
|   PostgreSQL 16 Engine   |               |   CampaignJobWorker Loop   |        | Communication &    |
| - 20+ Sales Tables      | <===========> | - SELECT FOR UPDATE SKIP   | =====> | CRM Providers      |
| - Foreign Key Cascades  |  (Job Queue)  |   LOCKED                   |        | - AWS SES (Email)  |
| - Alembic a1b2c3d4e5f7  |               | - Lease Fencing Tokens     |        | - Retell AI (Voice)|
| - Tenant Isolation      |               | - Idempotent Dispatch      |        | - Twilio (SMS)     |
+-------------------------+               +----------------------------+        | - MS Graph (Inbox) |
                                                                                | - HubSpot (CRM)    |
                                                                                +--------------------+
```

---

## 2. Sales Application Feature Inventory

Every verified Sales feature in the application is documented below, including its purpose, user interaction, frontend/backend architecture, and implementation status.

| Module | Feature Name | Status | Frontend Route / Component | Backend Route / Service | Entities Involved |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Dashboard** | Sales Executive Overview | Implemented & Verified | `/sales`<br>`src/app/sales/page.tsx`<br>`src/app/page.tsx` | `GET /api/v1/analytics/overview`<br>`analytics_service.py` | `Lead`, `Contact`, `Deal`, `Outreach`, `CallRecord` |
| **Prospecting** | Natural Language & Filter Search | Implemented & Verified | `/sales/find-leads`<br>`src/app/find-leads/page.tsx` | `POST /api/v1/leads/import`<br>`POST /api/v1/leads/select` | `Lead`, `IdealCustomerProfile` |
| **Lead Mgmt** | Lead Table & Detail Drawer | Implemented & Verified | `/sales/leads`<br>`LeadDetailDrawer.tsx` | `GET /api/v1/leads`<br>`GET /api/v1/leads/{id}` | `Lead`, `Company`, `Contact`, `LeadResearch` |
| **Lead Mgmt** | Lead Qualification & Scoring | Implemented & Verified | `LeadDetailDrawer.tsx`<br>`CRMLeadStatusBadge.tsx` | `POST /api/v1/leads/{id}/evaluate-qualification` | `Lead` |
| **Lead Mgmt** | Automated Lead Routing Rules | Implemented & Verified | `LeadDetailDrawer.tsx`<br>`routing-rules/` | `GET,POST /api/v1/routing-rules`<br>`routing_service.py` | `LeadRoutingRule`, `Lead`, `User` |
| **Lead Mgmt** | Lead-to-CRM Conversion | Implemented & Verified | `LeadDetailDrawer.tsx`<br>`(Convert Button)` | `POST /api/v1/leads/{id}/convert`<br>`lead_generation/service.py` | `Lead`, `Contact`, `Company` |
| **Lead Mgmt** | CSV Batch Import & Mapping | Implemented & Verified | `src/app/leads/page.tsx`<br>`csvParser.ts` | `POST /api/v1/leads/import`<br>`import_lead_batch` | `Lead`, `Organization` |
| **CRM** | Contact Management | Implemented & Verified | `src/app/contacts/`<br>`contact_service.py` | `GET,POST,PATCH,DELETE`<br>`/api/v1/contacts` | `Contact`, `Company` |
| **CRM** | Company & Account Management | Implemented & Verified | `src/app/companies/`<br>`company_service.py` | `GET,POST,PATCH,DELETE`<br>`/api/v1/companies` | `Company`, `Contact`, `Deal` |
| **Pipeline** | Deal Pipeline & Kanban Board | Implemented & Verified | `/sales/pipeline`<br>`src/app/pipeline/page.tsx` | `GET,POST /api/v1/pipelines`<br>`deal_service.py` | `Pipeline`, `PipelineStage`, `Deal` |
| **Pipeline** | Deal Movement & Close Status | Implemented & Verified | `DealDetailDrawer.tsx`<br>`CreateDealModal.tsx` | `PATCH /api/v1/deals/{id}/stage`<br>`PATCH /api/v1/deals/{id}/status` | `Deal`, `PipelineStage` |
| **Cadences** | Sales Outbound Cadence Builder | Implemented & Verified | `/sales/campaigns`<br>`workflow-builder.tsx` | `GET,POST /api/v1/campaigns`<br>`campaign_service.py` | `Campaign`, `CampaignStep`, `CampaignContact` |
| **Cadences** | Asynchronous Job Queue | Implemented & Verified | Background Daemon<br>`worker.py` | `job_service.py`<br>`worker.py` | `CampaignExecutionJob`, `Outreach` |
| **Outreach** | Multi-Channel Activity Stream | Implemented & Verified | `/sales/outreach`<br>`outreach-detail-drawer.tsx` | `GET /api/v1/outreach`<br>`GET /api/v1/outreach/{id}/events` | `Outreach`, `OutreachEvent` |
| **Voice SDR** | Retell AI Voice Dispatch & Status | Implemented & Verified | `/sales/integrations`<br>`voice/service.py` | `POST /api/v1/voice/simulate-mock-completion` | `CallRecord`, `Outreach`, `Contact` |
| **Voice SDR** | Retell Webhook & Follow-Up Engine | Implemented & Verified | API Webhook Endpoint<br>`voice_followup.py` | `POST /api/v1/voice/retell-webhook`<br>`VoiceFollowUpService` | `CallRecord`, `Outreach`, `CampaignContact` |
| **SMS** | 1-on-1 SMS & Twilio Webhook | Implemented & Verified | `/sales/integrations`<br>`sms_service.py` | `POST /api/v1/sms/webhook`<br>`POST /api/v1/sms/preview` | `SMSSuppression`, `InboundSMSMessage` |
| **Inbox** | Support Mailbox Sync (MS Graph) | Implemented & Verified | `/inbox`<br>`src/app/inbox/page.tsx` | `GET,POST /api/v1/inbound-emails`<br>`sync_service.py` | `InboundEmail`, `GraphSyncRun`, `Contact` |
| **Integrations**| HubSpot CRM Read-Only Sync | Implemented & Verified | `/sales/integrations`<br>`hubspot/sync.py` | `POST /api/v1/integrations/hubspot/sync` | `HubSpotSyncRun`, `Company`, `Contact`, `Deal` |
| **Integrations**| Assisted LinkedIn Outreach | Implemented & Verified | `/sales/integrations`<br>`linkedin/service.py` | `GET,POST /api/v1/integrations/linkedin/*` | `LinkedInConnection`, `LinkedInOAuthState` |
| **Governance**  | Channel Entitlements & Upgrades | Implemented & Verified | `/settings/entitlements`<br>`/admin/upgrades` | `GET,POST /api/v1/entitlements/*`<br>`entitlements_service.py` | `OrganizationChannelEntitlement`, `ChannelUpgradeRequest` |
| **Email AI**   | AI Email Template Generation | Implemented & Verified | `/sales/campaigns`<br>`template_renderer.py` | `POST /api/v1/templates/generate-ai`<br>`campaign_ai_service.py` | `EmailTemplate`, `CampaignStep` |

### Detailed Feature Descriptions

#### 1. Sales Executive Dashboard (`/sales`)
- **Purpose:** Gives sales reps and leadership immediate operational visibility into qualified leads, deal values, outreach engagement, and voice calling metrics.
- **User Interaction:** Displays 6 core KPI cards, a Recent Leads table with quick-view drawers, pipeline stage breakdowns, and direct action buttons ("Find Leads", "Add Lead", "Create Outreach").
- **Implementation:** React 19 Client Component fetching real tenant-isolated statistics via `/api/v1/analytics/overview` and CRM leads via `/api/v1/leads?exclude_test=true`.

#### 2. Lead Discovery & Management (`/sales/find-leads` & `/sales/leads`)
- **Purpose:** Centralized prospect ingestion, enrichment, qualification, and lifecycle tracking.
- **User Interaction:** Users search by ICP criteria (Industry, Location, Headcount, Title), inspect lead scores (0–100) and temperatures (`HOT`, `WARM`, `COLD`), review explainable AI qualification notes, and trigger single or bulk status updates.
- **Conversion Workflow:** With a single click ("Convert to Contact"), the system deduplicates the company by normalized domain, deduplicates the contact by normalized email, creates CRM `Company` and `Contact` records, links the lead, and updates the status to `converted`.

#### 3. Deal & Pipeline Management (`/sales/pipeline`)
- **Purpose:** Visual, interactive sales pipeline tracking with revenue forecasting.
- **User Interaction:** Kanban board view with drag-and-drop or modal stage progression (`Lead In`, `Contact Made`, `Meeting Scheduled`, `Proposal Sent`, `Negotiation`).
- **Safety & Validation:** Deals cannot move across pipelines accidentally. Negative amounts are blocked at both schema and DB constraint levels. Real-time metrics compute Total Pipeline Value, Weighted Expected Value, and Won Value.

#### 4. Asynchronous Sales Cadence Execution Engine
- **Purpose:** Reliable background execution of multi-day, multi-channel sales cadences.
- **Architecture:** Zero-delay and scheduled steps are committed as immutable `CampaignExecutionJob` records into PostgreSQL. The background `CampaignJobWorker` polls with `SELECT ... FOR UPDATE SKIP LOCKED`, acquires a unique `lease_token`, verifies worker ownership, and dispatches via SES or Retell.
- **Safety:** Stale jobs (>24h overdue) are placed in `held` status for manual SDR review, preventing accidental middle-of-the-night dispatch.

#### 5. AI Voice SDR Agent & Retell Integration
- **Purpose:** Autonomous AI phone agent that conducts qualifying discovery calls, answers objections, and captures meeting requests.
- **Webhook Follow-Up:** When Retell completes a call, the `POST /api/v1/voice/retell-webhook` endpoint verifies the HMAC-SHA256 signature, extracts structured variables (`interest_level`, `meeting_requested`, `callback_requested`), stores the `CallRecord`, and automatically sends an email follow-up containing the company's booking link within the same transaction.

#### 6. Microsoft Graph Support Mailbox Reconciliation (`/inbox`)
- **Purpose:** Automatically catches inbound replies sent to the company support mailbox (`support@agilereceivables.com`) that belong to active sales opportunities.
- **Implementation:** Polls Microsoft Graph API using Delta Links, creates `InboundEmail` records, automatically matches them to existing `Contact` or `Lead` records by email, and provides a triage UI for sales reps to mark messages as `approved`, `rejected`, or `escalated`.

---

## 3. Technology Stack

All technologies listed below have been verified against `backend/requirements.txt`, `frontend/package.json`, and active configuration files.

| Category | Technology | Verified Version | Purpose & Application in Sales |
| :--- | :--- | :--- | :--- |
| **Frontend Framework** | Next.js | `16.4.2` | App Router architecture, Server & Client components, BFF API proxy routes |
| **Frontend UI Library** | React / React-DOM | `19.3.0` | Modern concurrent rendering, hooks, client context state management |
| **Styling & CSS** | Tailwind CSS | `^3.4.17` | Utility-first styling with custom corporate theme and CSS variables |
| **Component Icons** | Lucide React | `^1.53.0` | Comprehensive icon set for navigation, channels, and statuses |
| **CSV Parsing** | PapaParse | `^5.7.0` | Client-side CSV streaming and column auto-detection for lead imports |
| **Backend Framework** | FastAPI | `>=0.115.0` | High-performance asynchronous REST API framework with Pydantic validation |
| **ASGI Server** | Uvicorn | `>=0.30.0` | Production ASGI web server supporting async lifespan event loops |
| **Language (Backend)** | Python | `3.13.x` (3.11+ compatible) | Core backend programming language |
| **Database Engine** | PostgreSQL | `16.x` | Relational database with JSONB, ACID transactions, and row-level locking |
| **ORM** | SQLAlchemy | `>=2.0.0` | Declarative 2.0 mapped models, session management, `with_for_update` locks |
| **DB Migrations** | Alembic | `>=1.14.0` | Schema version control (current head: `a1b2c3d4e5f7`) |
| **DB Driver** | Psycopg (binary) | `>=3.2.0` | Modern, high-performance PostgreSQL driver for Python |
| **Password Hashing** | Argon2-cffi | `>=23.1.0` | Memory-hard cryptographic password hashing algorithm |
| **Authentication** | PyJWT | `>=2.8.0` | Secure signing and verification of HS256 JSON Web Tokens |
| **HTTP Client** | HTTPX | `>=0.27.0` | Async and sync HTTP requests for Retell, Twilio, HubSpot, Graph, and SES |
| **Cloud SDK** | Boto3 | `>=1.34.0` | AWS SDK for SES email delivery, SNS webhook notifications, and Bedrock AI |
| **AI / LLM** | AWS Bedrock | `boto3` runtime | Bedrock Claude 3 Haiku / Sonnet for cold email copy and lead research |
| **Voice AI** | Retell AI API | Custom SDK / REST | Autonomous conversational AI voice agents with webhook callbacks |
| **SMS Infrastructure**| Twilio REST API | Custom HTTP client | 1-on-1 SMS outreach, E.164 phone validation, inbound opt-out handling |
| **CRM Integration** | HubSpot CRM API | v3 REST API | Read-only synchronization of Contacts, Companies, and Deals |
| **Mailbox Sync** | Microsoft Graph | v1.0 REST API | Delta query synchronization for M365 shared support mailboxes |
| **Testing** | Pytest | `>=8.0.0` | Comprehensive backend test suite with 69 verified test modules |

---

## 4. High-Level System Architecture

### 4.1 System Architecture Diagram
```mermaid
flowchart TD
    subgraph ClientLayer ["Client Presentation Layer (Browser)"]
        UI["Next.js 16 Web Application (React 19)"]
        Pages["Sales Dashboard | Leads | Pipeline | Outreach | Inbox | Integrations"]
    end

    subgraph BFFLayer ["Next.js Backend-For-Frontend (BFF)"]
        Proxy["Next.js Route Handlers (/api/*)"]
        AuthExtract["Token Extraction & Forwarding"]
    end

    subgraph BackendCore ["FastAPI Backend Application (/api/v1)"]
        Router["FastAPI APIRouter Aggregation"]
        Deps["Dependency Injection (Auth, Organization, DB Session)"]
        Services["Domain Services (Lead, Deal, Outreach, Voice, Scheduler)"]
    end

    subgraph BackgroundProcessing ["Asynchronous Processing"]
        Lifespan["FastAPI Lifespan Manager"]
        SchedulerService["CampaignSchedulerService Loop"]
        Worker["CampaignJobWorker Daemon"]
        GraphLoop["Microsoft Graph Auto-Sync Loop"]
    end

    subgraph Persistence ["Persistence Layer (PostgreSQL 16)"]
        DB[(agile_sales_marketing Database)]
        JobQueue["campaign_execution_jobs (SKIP LOCKED Queue)"]
        SalesTables["Leads | Contacts | Companies | Deals | Outreach | CallRecords"]
    end

    subgraph ExternalProviders ["External Communication & CRM Providers"]
        SES["AWS SES (Email Dispatch)"]
        Retell["Retell AI (Voice SDR Calls)"]
        Twilio["Twilio (SMS Gateway)"]
        HubSpot["HubSpot CRM v3"]
        Graph["Microsoft Graph API (M365)"]
        Bedrock["AWS Bedrock (Claude 3 AI)"]
    end

    UI --> Proxy
    Proxy --> Router
    Router --> Deps
    Deps --> Services
    Services --> Persistence
    Lifespan --> SchedulerService
    Lifespan --> Worker
    Lifespan --> GraphLoop
    SchedulerService --> JobQueue
    Worker --> JobQueue
    Worker --> SES
    Worker --> Retell
    Worker --> Twilio
    Services --> Bedrock
    Services --> HubSpot
    GraphLoop --> Graph
```

### 4.2 Frontend-to-Backend Request Flow
```mermaid
sequenceDiagram
    autonumber
    actor User as Sales Representative
    participant UI as Next.js Client Component
    participant BFF as Next.js API Route (/api/leads)
    participant FastAPIRoute as FastAPI Router (/api/v1/leads)
    participant AuthDep as get_current_organization Dependency
    participant Service as LeadService / DB Session
    participant DB as PostgreSQL Database

    User->>UI: Clicks "Convert Lead to Contact"
    UI->>BFF: POST /api/leads/{id}/convert (with auth_token cookie)
    BFF->>FastAPIRoute: Forward POST /api/v1/leads/{id}/convert (Bearer Token)
    FastAPIRoute->>AuthDep: Validate JWT & Extract organization_id
    AuthDep-->>FastAPIRoute: Verified Organization Context
    FastAPIRoute->>Service: convert_lead_to_crm(db, current_org, lead_id)
    Service->>DB: Query Lead (tenant-scoped)
    Service->>DB: Query / Insert Company (deduplicated by domain)
    Service->>DB: Query / Insert Contact (deduplicated by email)
    Service->>DB: Update Lead (status='converted', company_id, contact_id)
    DB-->>Service: Commit Transaction
    Service-->>FastAPIRoute: LeadConversionResponse
    FastAPIRoute-->>BFF: 200 OK JSON
    BFF-->>UI: 200 OK JSON
    UI-->>User: Display Success Notification & Open Contact Drawer
```

### 4.3 Database Entity-Relationship Overview
```mermaid
erDiagram
    ORGANIZATIONS ||--o{ USERS : "has members"
    ORGANIZATIONS ||--o{ LEADS : "owns"
    ORGANIZATIONS ||--o{ COMPANIES : "owns"
    ORGANIZATIONS ||--o{ CONTACTS : "owns"
    ORGANIZATIONS ||--o{ PIPELINES : "owns"
    ORGANIZATIONS ||--o{ DEALS : "owns"
    ORGANIZATIONS ||--o{ CAMPAIGNS : "owns"
    ORGANIZATIONS ||--o{ OUTREACH : "owns"
    ORGANIZATIONS ||--o{ CALL_RECORDS : "owns"
    ORGANIZATIONS ||--o{ CAMPAIGN_EXECUTION_JOBS : "owns"
    ORGANIZATIONS ||--o{ INBOUND_EMAILS : "owns"

    COMPANIES ||--o{ CONTACTS : "employs"
    COMPANIES ||--o{ DEALS : "associated with"
    CONTACTS ||--o{ DEALS : "primary contact"
    
    LEADS }o--|| COMPANIES : "converts to"
    LEADS }o--|| CONTACTS : "converts to"

    PIPELINES ||--o{ PIPELINE_STAGES : "contains"
    PIPELINE_STAGES ||--o{ DEALS : "current stage"

    CAMPAIGNS ||--o{ CAMPAIGN_STEPS : "defined by"
    CAMPAIGNS ||--o{ CAMPAIGN_CONTACTS : "enrolls"
    CONTACTS ||--o{ CAMPAIGN_CONTACTS : "enrolled in"

    CAMPAIGN_CONTACTS ||--o{ CAMPAIGN_EXECUTION_JOBS : "executes"
    CAMPAIGN_STEPS ||--o{ CAMPAIGN_EXECUTION_JOBS : "step blueprint"
    CAMPAIGN_EXECUTION_JOBS ||--o| OUTREACH : "dispatches"

    OUTREACH ||--o{ OUTREACH_EVENTS : "tracks"
    CALL_RECORDS ||--o| OUTREACH : "followup email"
```

### 4.4 Authentication Flow
```mermaid
sequenceDiagram
    autonumber
    actor User as Sales User
    participant LoginUI as /login (Next.js)
    participant AuthBFF as /api/auth/login
    participant Backend as FastAPI /api/v1/auth/login
    participant DB as PostgreSQL (users table)

    User->>LoginUI: Submits email & password
    LoginUI->>AuthBFF: POST {email, password}
    AuthBFF->>Backend: Forward credentials
    Backend->>DB: Query User by email
    DB-->>Backend: User record (hashed_password)
    Backend->>Backend: Verify Argon2id password hash
    Backend->>Backend: Sign Access JWT (30m, HS256) & Refresh JWT (14d)
    Backend-->>AuthBFF: Return tokens + User profile (role, access_level)
    AuthBFF-->>LoginUI: Set httpOnly cookies (auth_token, refresh_token)
    LoginUI->>User: Redirect to /sales Dashboard
```

### 4.5 Sales Communication Integration Flow
```mermaid
flowchart LR
    subgraph Engine ["Execution Engine"]
        Worker["CampaignJobWorker"]
    end

    subgraph EmailPath ["Email Channel"]
        SES["AWS SES"]
        SNS["AWS SNS Webhook"]
        Tracking["/api/v1/tracking/ses-webhook"]
    end

    subgraph VoicePath ["Voice Channel"]
        RetellClient["Retell AI API"]
        RetellHook["/api/v1/voice/retell-webhook"]
        Followup["VoiceFollowUpService"]
    end

    subgraph SMSPath ["SMS Channel"]
        TwilioClient["Twilio API"]
        TwilioHook["/api/v1/sms/webhook"]
        Suppression["SMSSuppression Table"]
    end

    Worker -->|Send Email| SES
    SES -->|Delivery/Bounce/Open| SNS
    SNS --> Tracking

    Worker -->|Trigger AI SDR Call| RetellClient
    RetellClient -->|Call Analyzed| RetellHook
    RetellHook --> Followup
    Followup -->|Send Booking Link| SES

    Worker -->|Send 1-on-1 SMS| TwilioClient
    TwilioClient -->|Incoming STOP / Opt-Out| TwilioHook
    TwilioHook --> Suppression
```

---

## 5. Frontend Architecture

### 5.1 Next.js 16 App Router Structure
The frontend is built using Next.js 16.4.2 with React 19. The application utilizes the Next.js App Router where routes are structured as directories under `frontend/src/app`.

```
frontend/src/
├── app/
│   ├── (auth)/login/page.tsx          # Login page with credentials form
│   ├── sales/page.tsx                 # Sales Dashboard (routes to app/page.tsx with forcedMode="sales")
│   ├── sales/find-leads/page.tsx      # Prospect search & lead discovery
│   ├── sales/leads/page.tsx           # Lead management table & detail drawers
│   ├── sales/pipeline/page.tsx        # Deal Kanban board & revenue pipeline
│   ├── sales/outreach/page.tsx        # Multi-channel outreach activity log
│   ├── sales/campaigns/page.tsx       # Sales outbound cadences & workflow builder
│   ├── sales/integrations/page.tsx    # HubSpot, Retell, Twilio, Poplar integration panel
│   ├── sales/analytics/page.tsx       # Sales operational metrics & charts
│   ├── sales/settings/page.tsx        # Organization & profile settings
│   ├── inbox/page.tsx                 # Support mailbox inbound email triage
│   ├── settings/entitlements/page.tsx # Customer channel upgrade requests
│   └── api/                           # Backend-For-Frontend (BFF) route handlers
├── components/
│   ├── layout/                        # AppShell, Sidebar, Header, PageHeader
│   ├── ui/                            # Button, Modal, Card, Table, Badge, Input, Select
│   ├── leads/                         # LeadDetailDrawer, LeadListsView, LeadListDetailView
│   ├── pipeline/                      # DealDetailDrawer, CreateDealModal
│   ├── campaigns/                     # WorkflowBuilder, CampaignDetailDrawer
│   └── outreach/                      # OutreachDetailDrawer, EventTimeline
├── contexts/
│   └── AppModeContext.tsx             # Controls 'sales' vs 'marketing' navigation & access levels
└── services/                          # Typed API client functions calling BFF endpoints
```

### 5.2 BFF (Backend-For-Frontend) Proxy Pattern
The frontend never exposes the internal backend URL directly to the browser. Instead, Next.js API Route Handlers in `src/app/api/*` act as a secure proxy:
1. The client browser makes requests to `/api/{resource}`.
2. The route handler calls `extractAuthToken(req)`, which reads the `auth_token` cookie or `Authorization` header.
3. The route handler attaches the bearer token and proxies the request to `BACKEND_URL` (`http://127.0.0.1:8000`).
4. Backend responses and error codes are returned cleanly to the client without exposing internal network topologies.

### 5.3 Mode Segregation: `AppModeContext`
`AppModeContext.tsx` enforces strict workspace separation between Sales and Marketing:
- User accounts have an `access_level`: `"sales"`, `"marketing"`, or `"both"`.
- If a user has `access_level: "sales"`, the application locks into Sales mode, and all marketing routes (`/marketing/*`, `/social-media`, `/content-calendar`) are hidden from navigation.
- If `access_level: "both"`, users can toggle between Sales and Marketing views via a switch in the sidebar.

### 5.4 State Management & Data Fetching
- **Server Data:** Managed with React hooks (`useState`, `useEffect`, `useCallback`) backed by asynchronous service functions in `src/services/`.
- **URL Synchronization:** Filter states (search queries, status filters, pagination offset) are synchronized with URL search parameters using `useSearchParams()` and `useRouter()`.
- **Optimistic Updates:** Kanban deal stage dragging updates the local UI immediately and reverts if the backend returns an error.

---

## 6. Backend Architecture

### 6.1 FastAPI Initialization & Lifespan Management
The FastAPI application entrypoint is located at `backend/app/main.py`. The backend runs with an asynchronous lifespan manager:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Start CampaignSchedulerService background loop (if SCHEDULER_ENABLED=True)
    # 2. Execute startup recovery tick to claim overdue steps immediately
    # 3. Start Microsoft Graph support mailbox auto-sync loop (if configured)
    yield
    # Clean shutdown of background tasks on SIGTERM / SIGINT
```

### 6.2 Router Organization & Versioning
All API endpoints are versioned under `/api/v1` and aggregated in `backend/app/api/v1/__init__.py`:
- `leads.py`, `lead_research.py`, `routing_rules.py`, `icp.py`
- `contacts.py`, `companies.py`, `deals.py`, `pipeline.py`
- `campaigns.py`, `campaign_steps.py`, `campaign_execution.py`
- `outreach.py`, `tracking.py`, `voice_webhook.py`, `sms.py`
- `inbound_emails.py`, `entitlements.py`, `email_templates.py`
- `integrations/hubspot.py`, `integrations/linkedin.py`

### 6.3 Dependency Injection & Tenant Isolation
FastAPI dependencies in `backend/app/api/deps.py` provide robust security and tenancy guarantees:
- `get_db()`: Yields an isolated SQLAlchemy session per request and ensures rollback on unhandled exceptions.
- `get_current_user()`: Validates the JWT access token from the header or cookie, decoding the user identity.
- `get_current_organization()`: Extracts the tenant authority strictly from the authenticated user's `organization_id` or token claims, preventing cross-tenant parameter tampering.
- `get_current_admin_user()`: Ensures administrative privileges for sensitive operations (channel unlocks, bulk deletes).

---

## 7. Database Architecture

The database is PostgreSQL 16 managed via SQLAlchemy 2.0 and Alembic migrations.

### 7.1 Core Sales Tables & Schema Reference

#### 1. `leads`
Stores inbound and discovered prospects prior to or during conversion.
- **Primary Key:** `id` (UUID)
- **Tenant Key:** `organization_id` (UUID -> `organizations.id` ON DELETE CASCADE)
- **Foreign Keys:**
  - `icp_id` (UUID -> `ideal_customer_profiles.id` ON DELETE SET NULL)
  - `company_id` (UUID -> `companies.id` ON DELETE SET NULL)
  - `contact_id` (UUID -> `contacts.id` ON DELETE SET NULL)
  - `assigned_to_user_id` (UUID -> `users.id` ON DELETE SET NULL)
  - `routing_rule_id` (UUID -> `lead_routing_rules.id` ON DELETE SET NULL)
- **Key Columns:** `company_name`, `company_domain`, `email`, `phone`, `job_title`, `lead_score` (0–100), `lead_temperature` (`HOT`, `WARM`, `COLD`), `qualification_status` (`unqualified`, `in_review`, `qualified`, `disqualified`), `status` (`new`, `selected`, `enrolled`, `contacted`, `replied`, `converted`, `rejected`), `is_test` (BOOLEAN).
- **Constraints & Indexes:** `ck_lead_score_range` (0 <= score <= 100), `uq_leads_org_source_ext`, composite indexes on `(organization_id, status)` and `(organization_id, email)`.

#### 2. `contacts`
Converted and verified individual CRM contacts.
- **Primary Key:** `id` (UUID)
- **Tenant Key:** `organization_id` (UUID -> `organizations.id` ON DELETE CASCADE)
- **Foreign Keys:** `company_id` (UUID -> `companies.id` ON DELETE SET NULL)
- **Key Columns:** `first_name`, `last_name`, `email`, `phone`, `job_title`, `lead_status`, `is_test` (BOOLEAN), `hubspot_id` (VARCHAR), address fields (`address_line_1`, `city`, `state`, `postal_code`, `country`), `linkedin_profile_url`.
- **Indexes:** Unique lower-case email index `ix_contacts_org_lower_email` per organization, index on `hubspot_id`.

#### 3. `companies`
Account-level organizations employing contacts.
- **Primary Key:** `id` (UUID)
- **Tenant Key:** `organization_id` (UUID -> `organizations.id` ON DELETE CASCADE)
- **Key Columns:** `name`, `domain`, `industry`, `employee_count_range`, `city`, `country`, `hubspot_id`.
- **Indexes:** Index on `(organization_id, domain)` and `(organization_id, hubspot_id)`.

#### 4. `deals`
Revenue opportunities tracked through sales pipeline stages.
- **Primary Key:** `id` (UUID)
- **Tenant Key:** `organization_id` (UUID -> `organizations.id` ON DELETE CASCADE)
- **Foreign Keys:**
  - `pipeline_stage_id` (UUID -> `pipeline_stages.id` ON DELETE RESTRICT)
  - `contact_id` (UUID -> `contacts.id` ON DELETE SET NULL)
  - `company_id` (UUID -> `companies.id` ON DELETE SET NULL)
- **Key Columns:** `name`, `amount` (NUMERIC(14,2)), `expected_close_date`, `status` (`open`, `won`, `lost`), `hubspot_id`.
- **Constraints:** `ck_deals_amount_non_negative` (`amount >= 0`).

#### 5. `pipelines` & `pipeline_stages`
Sales pipeline structures and sequential probability stages.
- **Pipelines:** `id`, `organization_id`, `name`, `is_default` (BOOLEAN).
- **Pipeline Stages:** `id`, `pipeline_id` (FK ON DELETE CASCADE), `name`, `order_index` (INT), `probability_pct` (INT, 0–100).
- **Constraints:** `ck_pipeline_stages_probability_pct` (`0 <= probability_pct <= 100`).

#### 6. `campaign_execution_jobs` (Migration `a1b2c3d4e5f7`)
Durable persistent queue for asynchronous campaign step execution.
- **Primary Key:** `id` (UUID)
- **Tenant Key:** `organization_id` (UUID -> `organizations.id` ON DELETE CASCADE)
- **Foreign Keys:**
  - `campaign_id` (UUID -> `campaigns.id` ON DELETE SET NULL)
  - `campaign_contact_id` (UUID -> `campaign_contacts.id` ON DELETE SET NULL)
  - `contact_id` (UUID -> `contacts.id` ON DELETE SET NULL)
  - `campaign_step_id` (UUID -> `campaign_steps.id` ON DELETE SET NULL)
  - `outreach_id` (UUID -> `outreach.id` ON DELETE SET NULL)
- **Queue Control Columns:** `status` (`pending`, `processing`, `completed`, `failed`, `retry_scheduled`, `held`, `dispatch_unknown`), `channel` (`email`, `voice`, `sms`), `scheduled_at`, `attempts`, `max_attempts` (default 3), `lease_token` (UUID fencing token), `leased_at`, `lease_expires_at`, `heartbeat_at`, `idempotency_key` (VARCHAR(255) UNIQUE).
- **Payload & Snapshots:** `execution_payload` (JSONB - immutable frozen rendered templates and channel parameters), `campaign_name_snapshot`, `recipient_snapshot`.
- **Indexes:** `ix_campaign_execution_jobs_poll` on `(status, scheduled_at)` with status filter for rapid worker polling; `ix_campaign_execution_jobs_lease_recovery` on `(status, lease_expires_at)` for reclaiming crashed worker leases.

#### 7. `call_records`
Full transcripts, AI analysis, and structured outcomes from Retell AI voice SDR calls.
- **Primary Key:** `id` (UUID)
- **Tenant Key:** `organization_id` (UUID -> `organizations.id` ON DELETE CASCADE)
- **Foreign Keys:** `contact_id`, `lead_id`, `campaign_id`, `followup_email_id` (-> `outreach.id`).
- **Key Columns:** `call_id` (Retell UUID), `agent_id`, `direction` (`inbound`, `outbound`), `call_status`, `call_outcome` (`INTERESTED`, `QUALIFIED`, `MEETING_REQUESTED`, `CALLBACK_REQUESTED`, `NOT_INTERESTED`, `DO_NOT_CONTACT`, etc.), `duration_ms`, `summary`, `transcript`, `collected_variables` (JSONB), `followup_status` (`pending`, `sent`, `skipped`, `failed`), `followup_idempotency_key` (UNIQUE).

#### 8. `outreach` & `outreach_events`
Multi-channel dispatch logs and chronological interaction audit events.
- **Outreach:** `id`, `organization_id`, `campaign_id`, `contact_id`, `campaign_contact_id`, `call_record_id`, `channel` (`email`, `voice`, `sms`, `linkedin`, `physical_mail`), `status` (`draft`, `scheduled`, `sending`, `sent`, `failed`, `cancelled`), `sent_at`, `first_delivered_at`, `first_opened_at`, `first_clicked_at`, `first_replied_at`, `first_bounced_at`.
- **Outreach Events:** `id`, `organization_id`, `outreach_id`, `event_type` (`scheduled`, `sent`, `delivered`, `opened`, `clicked`, `replied`, `bounced`, `failed`, `held`), `event_metadata` (JSONB), `occurred_at`.

#### 9. `inbound_emails`
Support mailbox messages synced via Microsoft Graph.
- **Primary Key:** `id` (UUID)
- **Tenant Key:** `organization_id` (UUID -> `organizations.id` ON DELETE CASCADE)
- **Foreign Keys:** `matched_contact_id`, `matched_lead_id`, `matched_company_id`.
- **Key Columns:** `graph_message_id` (UNIQUE per org), `sender_email`, `sender_name`, `subject`, `body_preview`, `received_at`, `sync_status` (`imported`, `matched`, `unmatched`), `manual_review_status` (`pending`, `approved`, `rejected`, `escalated`).

### 7.2 Test Data Separation & QA Safeguards
To prevent synthetic test records from corrupting operational CRM views:
1. Every `Contact` and `Lead` table contains an `is_test` boolean flag.
2. `classify_is_test()` automatically scans names, email domains (`@blackmesa.org`, `@testacme.com`), and ingestion sources.
3. Operational production organization `0d85dc9f-1520-4bcb-8af4-8aad025255cb` is protected by `assert_safe_test_organization()` in `backend/app/core/qa_safeguard.py`. Any test script attempting to mutate this organization immediately raises `ProductionDataProtectionError`.
4. Dedicated QA Sandbox organization `c0aae7f1-95bb-485f-bb9b-e3ed95469912` is used for all automated tests, mock dispatching, and QA drills.


---

## 8. Sales Workflows – End to End

### 8.1 Lead Management Lifecycle
```mermaid
sequenceDiagram
    autonumber
    actor SDR as Sales Representative
    participant LeadUI as /sales/leads (Next.js)
    participant LeadService as LeadService (FastAPI)
    participant Scoring as Scoring Engine
    participant Routing as Routing Service
    participant CRM as CRM Service
    participant DB as PostgreSQL

    Note over SDR,DB: Phase 1: Ingestion & Scoring
    SDR->>LeadUI: Imports CSV or Creates Lead
    LeadUI->>LeadService: POST /api/v1/leads
    LeadService->>Scoring: calculate_lead_score(lead, icp)
    Scoring-->>LeadService: Score (85), Temp ('HOT'), Explainable Reason
    LeadService->>DB: Insert Lead (status='new', is_test=False)

    Note over SDR,DB: Phase 2: Qualification & Routing
    SDR->>LeadUI: Requests AI Qualification or Batch Route
    LeadUI->>LeadService: POST /api/v1/leads/{id}/evaluate-qualification
    LeadService->>Routing: route_lead(db, org_id, lead_id)
    Routing->>DB: Query LeadRoutingRules (ordered by priority)
    Routing-->>LeadService: Matches Rule #1 -> Assigns to SDR User
    LeadService->>DB: Update Lead (assigned_to_user_id, status='selected')

    Note over SDR,DB: Phase 3: CRM Conversion
    SDR->>LeadUI: Clicks "Convert to Contact"
    LeadUI->>LeadService: POST /api/v1/leads/{id}/convert
    LeadService->>CRM: convert_lead_to_crm(db, org, lead_id)
    CRM->>DB: Find/Create Company (dedup by normalized domain)
    CRM->>DB: Find/Create Contact (dedup by lower email)
    CRM->>DB: Update Lead (status='converted', company_id, contact_id)
    DB-->>LeadService: Transaction Committed
    LeadService-->>LeadUI: Return Converted Contact & Company details
```

### 8.2 Deal Management & Pipeline Progression
1. **Creation:** A deal is created either from a converted contact's detail drawer or directly on the `/sales/pipeline` board via `CreateDealModal`.
2. **Tenant Validation:** `deal_service.py` validates that `pipeline_stage_id`, `contact_id`, and `company_id` all belong strictly to the authenticated tenant.
3. **Stage Movement:** When a deal progresses (e.g., from *Proposal Sent* to *Negotiation*), the client calls `PATCH /api/v1/deals/{deal_id}/stage`. The backend verifies the target stage exists within the same pipeline, preventing accidental cross-pipeline corruption.
4. **Win/Loss Settlement:** Setting deal status to `won` or `lost` records the close timestamp, updates the pipeline won value, and stops any active outbound prospecting cadences for that contact.

### 8.3 Asynchronous Sales Cadence Execution
```mermaid
sequenceDiagram
    autonumber
    participant UI as Workflow Builder (/sales/campaigns)
    participant Sched as CampaignSchedulerService
    participant Queue as campaign_execution_jobs Table
    participant Worker as CampaignJobWorker Loop
    participant SES as AWS SES / Provider
    participant DB as PostgreSQL

    UI->>Sched: Enroll Contact & Activate Campaign
    Sched->>Sched: Evaluate Step 1 (Delay = 0h)
    Sched->>Queue: Enqueue Job (status='pending', frozen execution_payload)
    Note over Worker,Queue: Asynchronous Worker Loop
    Worker->>Queue: SELECT ... FOR UPDATE SKIP LOCKED
    Queue-->>Worker: Claims Job & Issues lease_token UUID
    Worker->>Worker: Validate Tenant Authorization & Overdue Staleness Gate
    Worker->>SES: Dispatch Email with rendered templates & booking link
    SES-->>Worker: 200 OK (MessageId returned)
    Worker->>DB: Insert Outreach (status='sent') & OutreachEvent ('sent')
    Worker->>Queue: Mark Job (status='completed')
    Worker->>Sched: advance_campaign_contact_sequence()
    Sched->>Queue: Enqueue Step 2 (e.g. AI Call scheduled in 2 days)
```

### 8.4 Retell AI Voice SDR Calling & Automated Follow-Up
```mermaid
sequenceDiagram
    autonumber
    participant Sched as CampaignScheduler
    participant Retell as Retell AI API
    participant Webhook as /api/v1/voice/retell-webhook
    participant Followup as VoiceFollowUpService
    participant SES as AWS SES
    participant DB as PostgreSQL

    Sched->>Retell: Initiate Outbound Call (phone, agent_id, dynamic vars)
    Note over Retell: AI Agent conducts conversation with prospect
    Retell->>Webhook: POST call_analyzed payload (HMAC-SHA256 signature)
    Webhook->>Webhook: Verify x-retell-signature using RETELL_WEBHOOK_SECRET
    Webhook->>Followup: process_call_analyzed(db, payload)
    Followup->>DB: Persist CallRecord (transcript, analysis, outcome)
    
    alt Prospect Interested / Meeting Requested
        Followup->>SES: Dispatch Follow-Up Email (includes booking link)
        Followup->>DB: Insert Outreach & Link to CallRecord
        Followup->>DB: Update CallRecord (followup_status='sent')
        Followup->>Sched: advance_campaign_contact_sequence() -> Step 3
    else Prospect Not Interested / Do Not Contact
        Followup->>DB: Update CampaignContact (enrollment_status='completed' or 'stopped')
        Followup->>DB: Update Contact (lead_status='do_not_contact')
    end
```

### 8.5 Inbound Email & Support Mailbox Reconciliation
1. **Background Loop:** When enabled, `run_graph_auto_sync_loop()` polls Microsoft Graph every 10 minutes using delta links.
2. **Ingestion & Matching:** New messages are stored in `inbound_emails`. The system matches the sender against `contacts.email` and `leads.email`.
3. **Inbox Triage:** Sales reps review unmatched or question-bearing messages in `/inbox`, view the associated lead/deal context, and mark reviews as `approved` or `escalated`.

### 8.6 Twilio SMS Outreach & Inbound Opt-Out Handling
1. **Phone Normalization:** All contact numbers are formatted into standard E.164 (`+1XXXXXXXXXX`) before dispatch.
2. **Suppression Pre-Flight:** Before queuing or sending SMS, the system queries `sms_suppressions`. If the phone is suppressed, dispatch is immediately aborted.
3. **Inbound Webhook (`/api/v1/sms/webhook`):** When a prospect texts `STOP`, `UNSUBSCRIBE`, `CANCEL`, or `QUIT`, Twilio posts to the webhook. The service:
   - Records the incoming message in `inbound_sms_messages`.
   - Inserts the normalized number into `sms_suppressions`.
   - Automatically pauses or stops active SMS cadences for that contact.

---

## 9. External Integrations

| Integration | Primary Purpose | Status | Authentication | Fail-Closed Safety Guard | Data Exchanged |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **AWS SES** | Cold outbound email delivery & tracking | Operational | IAM Credentials / AWS SDK | `EMAIL_PROVIDER_TYPE` fallback to `MockEmailProvider` | Recipient email, rendered HTML/text, Message ID, bounce/open/click telemetry |
| **Retell AI** | Conversational AI voice SDR agents | Operational | API Key (`Bearer`) + HMAC-SHA256 Webhook Secret | `RETELL_ENABLED` & `RETELL_ALLOW_LIVE_CALLS` | Phone numbers, agent IDs, dynamic prompts, call audio transcripts, sentiment analysis |
| **Twilio** | 1-on-1 SMS delivery & opt-out tracking | Operational | Account SID & Auth Token (HTTP Basic) | `TWILIO_ENABLED` & `TWILIO_ALLOW_LIVE_SENDING` | Destination E.164 phone, message body, Message SID, opt-out keywords |
| **HubSpot CRM**| Read-only sync of Contacts, Companies, Deals | Operational (Phase 1) | Private App Access Token (`Bearer`) | Read-Only implementation: zero writes to external CRM | Contacts, Companies, Deals, pipeline stages, lead statuses |
| **Microsoft Graph**| Support shared-mailbox sync (`support@`) | Operational | OAuth 2.0 Client Credentials / Delegated | `MICROSOFT_GRAPH_ENABLED` & `MICROSOFT_GRAPH_AUTO_SYNC_ENABLED` | Email messages, subject, body, sender, internet message ID, delta links |
| **AWS Bedrock** | AI cold email copy & prospect research | Operational | IAM / AWS Boto3 Bedrock Runtime | Region & Model fallback | Business profiles, ICP guidelines, prospect summaries, generated copy |
| **Poplar** | Automated physical postcard/letter dispatch | Operational (Live Sending Blocked) | API Key (Test / Production) | `POPLAR_ENABLED` & `POPLAR_ALLOW_LIVE_SENDING` (Forced False in testing) | Postal addresses, creative template IDs, pre-flight audit proofs |
| **LinkedIn** | Member OIDC auth & assisted outreach | Operational | OAuth 2.0 OpenID Connect & Encrypted Tokens | Scopes restricted to `openid profile email`; manual confirmation required | Member profile, member ID, profile URL, connection status |

---

## 10. API Documentation

### 10.1 Authentication & Session (`/api/v1/auth`)
- `POST /api/v1/auth/login`: Authenticates credentials; returns Access & Refresh JWTs and user profile.
- `POST /api/v1/auth/refresh`: Exchanges valid refresh token for a new access token.
- `GET /api/v1/auth/me`: Retrieves current authenticated user and organization details.
- `POST /api/v1/auth/logout`: Clears session tokens.

### 10.2 Leads & Prospecting (`/api/v1/leads`)
- `GET /api/v1/leads`: Paginated lead list with filtering by `status`, `qualification_status`, `temperature`, and `exclude_test`.
- `POST /api/v1/leads`: Creates a new prospect lead with automated ICP scoring.
- `POST /api/v1/leads/import`: Ingests a batch of CSV leads with column mapping and deduplication.
- `GET /api/v1/leads/{lead_id}`: Retrieves comprehensive lead profile and research context.
- `PATCH /api/v1/leads/{lead_id}`: Updates lead attributes.
- `POST /api/v1/leads/{lead_id}/convert`: **Converts lead into CRM Contact & Company records**.
- `POST /api/v1/leads/{lead_id}/evaluate-qualification`: Runs heuristic/AI qualification rules.
- `POST /api/v1/leads/{lead_id}/route`: Evaluates active `LeadRoutingRules` and assigns lead.
- `DELETE /api/v1/leads/{lead_id}`: Deletes a lead.

### 10.3 Contacts & Companies (`/api/v1/contacts` & `/api/v1/companies`)
- `GET /api/v1/contacts`: Lists CRM contacts with company associations and test filters.
- `POST /api/v1/contacts`: Manually creates a verified contact.
- `PATCH /api/v1/contacts/{contact_id}`: Updates contact details (phone, email, address).
- `DELETE /api/v1/contacts/{contact_id}`: Removes contact (handles dependent jobs safely).
- `GET /api/v1/companies`: Lists account-level companies.
- `POST /api/v1/companies`: Creates a company record.
- `PATCH /api/v1/companies/{company_id}`: Updates company industry, size range, or domain.

### 10.4 Sales Pipeline & Deals (`/api/v1/pipelines` & `/api/v1/deals`)
- `GET /api/v1/pipelines`: Retrieves organization pipelines and ordered stages.
- `POST /api/v1/pipelines`: Creates a new pipeline structure.
- `GET /api/v1/deals`: Lists deals with filters for `pipeline_id`, `stage_id`, and `status`.
- `POST /api/v1/deals`: Creates a deal associated with contact and company.
- `PATCH /api/v1/deals/{deal_id}/stage`: Moves deal across stages (recalculates weighted pipeline).
- `PATCH /api/v1/deals/{deal_id}/status`: Sets deal status to `open`, `won`, or `lost`.

### 10.5 Sales Cadences & Execution (`/api/v1/campaigns`)
- `GET /api/v1/campaigns`: Lists campaigns (filtered by `type="sales_outbound"`).
- `POST /api/v1/campaigns`: Creates a sales cadence blueprint.
- `GET,POST /api/v1/campaigns/{id}/steps`: Manages sequential touchpoint steps (Email, Voice, SMS).
- `POST /api/v1/campaigns/{id}/activate`: Activates cadence and enqueues initial zero-delay jobs.
- `POST /api/v1/campaigns/{id}/pause`: Halts automated execution.
- `POST /api/v1/campaigns/{id}/contacts/bulk`: Enrolls a batch of contacts into the cadence.
- `GET /api/v1/campaigns/scheduler/status`: Returns scheduler heartbeat and active queue metrics.
- `GET /api/v1/campaigns/scheduler/held`: Lists jobs held by the overdue staleness gate.
- `POST /api/v1/campaigns/scheduler/held/{outreach_id}/approve`: Manually approves a held job for immediate dispatch.

### 10.6 Communication & Webhooks
- `GET /api/v1/outreach`: Chronological log of all sent, scheduled, and delivered touchpoints.
- `POST /api/v1/voice/retell-webhook`: Ingests Retell AI call completion events and triggers follow-ups.
- `POST /api/v1/sms/webhook`: Ingests Twilio SMS status callbacks and inbound opt-out texts.
- `POST /api/v1/tracking/ses-webhook`: Ingests AWS SNS delivery, bounce, and complaint notifications.
- `GET /api/v1/inbound-emails`: Lists inbound support emails with matched sales entities.
- `POST /api/v1/inbound-emails/sync`: Triggers manual incremental sync with Microsoft Graph.
- `POST /api/v1/integrations/hubspot/sync`: Triggers manual read-only sync from HubSpot CRM.

---

## 11. Authentication, Authorization and Security

### 11.1 Token Cryptography & Sessions
- **Access Tokens:** Signed using HMAC-SHA256 (`HS256`) with a cryptographically verified `SECRET_KEY` (minimum 32 characters; default placeholder keys are rejected at startup). Access tokens expire in 30 minutes.
- **Refresh Tokens:** Long-lived tokens (14-day validity) stored in `httpOnly`, `SameSite=Lax` cookies, exchangeable via `POST /api/v1/auth/refresh`.
- **Password Security:** Hashes are generated using Argon2id (`argon2-cffi`), protecting against GPU and ASIC cracking attacks.

### 11.2 Multi-Tenant Data Isolation
- Every core database table includes an `organization_id` foreign key referencing `organizations.id`.
- The FastAPI dependency `get_current_organization` validates that the user's token identity matches the requested resource tenant.
- All database queries explicitly filter by `Model.organization_id == current_org.id`.
- Foreign key actions default to `ON DELETE CASCADE` for tenant accounts or `ON DELETE SET NULL` for non-critical relationships, ensuring that orphaned pending jobs cannot execute.

### 11.3 Webhook HMAC Signatures
All public webhook receivers verify cryptographic signatures before processing payloads:
- **Retell AI:** Verifies `x-retell-signature` using HMAC-SHA256 and `RETELL_WEBHOOK_SECRET`.
- **Twilio SMS:** Verifies `X-Twilio-Signature` using standard Twilio request validator.
- **AWS SNS / SES:** Validates AWS SNS X.509 signing certificates and authenticates topic ARNs before accepting delivery or bounce webhooks.

### 11.4 Sensitive Data & PII Protection
- API keys (`SECRET_KEY`, `RETELL_API_KEY`, `TWILIO_AUTH_TOKEN`, `HUBSPOT_ACCESS_TOKEN`) are configured with `repr=False` in Pydantic settings to prevent accidental exposure in stack traces or logs.
- LinkedIn access tokens stored in the database are encrypted at rest using Fernet symmetric encryption.
- Execution payloads frozen in `campaign_execution_jobs` only snapshot non-sensitive template fields and recipient email/name strings.

---

## 12. Background Jobs and Asynchronous Processing

### 12.1 Persistent Job Queue (`campaign_execution_jobs`)
To eliminate the vulnerability of lost executions or request timeouts during multi-step sales cadences, the application utilizes a persistent PostgreSQL-backed queue introduced in migration `a1b2c3d4e5f7`.

### 12.2 Atomic Job Claiming (`SELECT ... FOR UPDATE SKIP LOCKED`)
The worker polls eligible jobs using:
```sql
SELECT * FROM campaign_execution_jobs
WHERE status IN ('pending', 'retry_scheduled')
  AND scheduled_at <= NOW()
ORDER BY scheduled_at ASC
FOR UPDATE SKIP LOCKED
LIMIT :batch_size;
```
`SKIP LOCKED` allows multiple worker threads or containers to poll simultaneously without blocking each other and without duplicate job claims.

### 12.3 Fencing Tokens & Worker Leases
When a job is claimed:
1. The worker writes a unique UUID `lease_token`, its `worker_id`, and sets `lease_expires_at = NOW() + 5 minutes`.
2. While executing, the worker emits heartbeats to extend the lease.
3. When completing or failing the job, the update query verifies `WHERE id = :id AND lease_token = :lease_token`. If another worker reclaimed the job after a timeout, the write fails cleanly with `LeaseLostError`.

### 12.4 Ambiguous Outcomes (`dispatch_unknown`)
If an external provider (such as SES or Retell) accepts a request but the worker process crashes before persisting success, the job enters the `dispatch_unknown` reconciliation state. The system never blindly retries an ambiguous dispatch, avoiding double-calling or double-emailing prospects.

### 12.5 Overdue Staleness Gate
If an outbound job is delayed by more than `SCHEDULER_MAX_OVERDUE_HOURS` (24 hours)—e.g., due to an extended database maintenance window—the scheduler automatically transitions the job to `status='held'`. Sales reps can review held jobs at `/api/v1/campaigns/scheduler/held` and manually approve or dismiss them.


---

## 13. Testing and Quality Assurance

### 13.1 Backend Test Architecture
The backend testing infrastructure is powered by `pytest` and located in `backend/tests/`. The suite comprises **69 verified test modules** covering:
- Unit tests for domain models, validation schemas, and scoring heuristics.
- Integration tests for database queries, foreign key cascading, and unique constraints.
- End-to-end integration tests for asynchronous campaign execution, scheduler lifecycle, Retell webhook processing, and HubSpot sync.

### 13.2 Mock Communication Providers
To ensure zero accidental outbound communication during testing:
- **Email:** Tests utilize `MockEmailProvider` (`backend/app/services/outreach/base.py`), which stores dispatched emails in an in-memory list without initiating network calls.
- **Voice SDR:** Tests utilize mock Retell API responses and simulate call completions via `POST /api/v1/voice/simulate-mock-completion`.
- **SMS:** Twilio client calls are intercepted by mock providers asserting that `TWILIO_ALLOW_LIVE_SENDING` is `False`.
- **Physical Mail:** Poplar test client operates in `sandbox` mode with verified mock responses.

### 13.3 Test Organizations & Environment Isolation
- **Operational Production Tenant:** `0d85dc9f-1520-4bcb-8af4-8aad025255cb` (`agile-sales-marketing-org`).
  - Protected by `assert_safe_test_organization()` in `backend/app/core/qa_safeguard.py`.
  - Any test attempting to modify this organization immediately aborts with `ProductionDataProtectionError`.
- **Dedicated QA Sandbox Tenant:** `c0aae7f1-95bb-485f-bb9b-e3ed95469912` (`agile-qa-sandbox-org`).
  - The authorized organization for all automated tests, mock dispatching, and manual exploratory testing.

### 13.4 Running Backend Tests
Execute the following commands from the repository root:
```powershell
# Set PYTHONPATH to the backend directory
$env:PYTHONPATH="D:\Agile-Sales-Marketing\backend"

# Run the complete test suite
pytest backend/tests -v

# Run asynchronous campaign execution tests
pytest backend/tests/test_async_campaign_execution_jobs.py -v

# Run Retell voice webhook & workflow progression tests
pytest backend/tests/test_retell_voice_webhook_and_workflow.py -v

# Run HubSpot synchronization tests
pytest backend/tests/test_hubspot_sync.py -v
```

### 13.5 Frontend Testing Status
- The frontend currently utilizes Next.js ESLint (`npm run lint`) for static analysis and type checks (`typescript: ^5`).
- There is currently no Jest, Vitest, or Playwright configuration in `frontend/package.json`. Frontend quality assurance is currently conducted via integration testing through the BFF proxy and manual browser testing.

---

## 14. Local Development Setup

A complete setup guide for getting the Agile Sales application running locally on a development workstation.

### 14.1 Prerequisites
- **Node.js:** `v20.x` or later
- **Python:** `3.11` or `3.13`
- **PostgreSQL:** `16.x` installed and running locally on port 5432
- **Git**

### 14.2 Database Preparation
1. Create a local PostgreSQL database:
   ```sql
   CREATE DATABASE agile_sales_marketing;
   ```
2. Verify local user credentials match your local connection string.

### 14.3 Backend Installation & Startup
```powershell
# 1. Navigate to backend directory
cd D:\Agile-Sales-Marketing\backend

# 2. Create and activate a Python virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install backend dependencies
pip install -r requirements.txt

# 4. Set environment variable for module resolution
$env:PYTHONPATH="D:\Agile-Sales-Marketing\backend"

# 5. Apply all database migrations to head revision (a1b2c3d4e5f7)
python -m alembic -c alembic.ini upgrade head

# 6. Start the FastAPI development server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 14.4 Frontend Installation & Startup
```powershell
# 1. Open a new terminal and navigate to frontend directory
cd D:\Agile-Sales-Marketing\frontend

# 2. Install Node dependencies
npm install

# 3. Start Next.js development server
npm run dev
```

### 14.5 Environment Configuration Guide (`.env`)
Create a `.env` file in `D:\Agile-Sales-Marketing\backend/.env` based on the following template (do **NOT** commit real secret values):

```ini
# General Application Settings
PROJECT_NAME="Agile Sales & Marketing API"
ENVIRONMENT="development"
DEBUG=True
API_V1_STR="/api/v1"

# Database Connection
DATABASE_URL="postgresql+psycopg://postgres:yourpassword@localhost:5432/agile_sales_marketing"

# Security & JWT (Must be at least 32 characters; random string)
SECRET_KEY="generate-a-strong-random-secret-key-at-least-32-chars-long"
JWT_ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=14

# CORS Allowed Origins
CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"

# Background Scheduler & Asynchronous Job Execution
SCHEDULER_ENABLED=True
SCHEDULER_INTERVAL_SECONDS=10
SCHEDULER_BATCH_SIZE=25
SCHEDULER_AUTO_DISPATCH=True
SCHEDULER_MAX_OVERDUE_HOURS=24
SCHEDULER_AUTHORIZED_ORGS="c0aae7f1-95bb-485f-bb9b-e3ed95469912"

# Outbound Email Configuration (AWS SES or mock)
EMAIL_PROVIDER_TYPE="mock"
AWS_SES_REGION="us-east-2"
AWS_SES_FROM_EMAIL="sales@agilereceivables.com"

# Retell AI Voice Configuration
RETELL_API_KEY=""
RETELL_AGENT_ID=""
RETELL_WEBHOOK_SECRET="your-retell-webhook-secret"
RETELL_ENABLED=False
RETELL_ALLOW_LIVE_CALLS=False

# Twilio SMS Configuration
TWILIO_ACCOUNT_SID=""
TWILIO_AUTH_TOKEN=""
TWILIO_FROM_NUMBER=""
TWILIO_ENABLED=False
TWILIO_ALLOW_LIVE_SENDING=False

# HubSpot CRM Integration
HUBSPOT_ACCESS_TOKEN=""

# Microsoft Graph Support Mailbox Sync
MICROSOFT_GRAPH_ENABLED=False
MICROSOFT_GRAPH_AUTO_SYNC_ENABLED=False
MICROSOFT_GRAPH_TENANT_ID=""
MICROSOFT_GRAPH_CLIENT_ID=""
MICROSOFT_GRAPH_CLIENT_SECRET=""
```

### 14.6 Local Application URLs
- **Sales Dashboard:** `http://localhost:3000/sales`
- **Lead Discovery:** `http://localhost:3000/sales/find-leads`
- **Leads Table:** `http://localhost:3000/sales/leads`
- **Sales Pipeline:** `http://localhost:3000/sales/pipeline`
- **Support Inbox:** `http://localhost:3000/inbox`
- **Integrations Panel:** `http://localhost:3000/sales/integrations`
- **FastAPI OpenAPI Swagger UI:** `http://127.0.0.1:8000/docs`
- **FastAPI ReDoc:** `http://127.0.0.1:8000/redoc`
- **Backend Health Check:** `http://127.0.0.1:8000/health`

### 14.7 Common Startup Troubleshooting
1. **Alembic `ModuleNotFoundError: No module named 'app'`:**
   - *Cause:* Python cannot resolve the application root when running Alembic.
   - *Fix:* Ensure `$env:PYTHONPATH="D:\Agile-Sales-Marketing\backend"` is set before executing Alembic commands.
2. **FastAPI Insecure Secret Error at Startup:**
   - *Cause:* `SECRET_KEY` is empty, shorter than 32 characters, or contains a default placeholder like `"secret"` or `"changeme"`.
   - *Fix:* Supply a strong 32+ character random string in `.env`.
3. **CORS / Network Error in Browser:**
   - *Cause:* Browser requesting `http://127.0.0.1:8000` directly rather than through the Next.js BFF proxy `/api/*`.
   - *Fix:* Ensure all frontend calls target `/api/...` so the Next.js API route proxies the request with auth tokens.

---

## 15. Deployment and Infrastructure

### 15.1 Architecture & Hosting Model
The application is designed for containerized or PaaS cloud deployment (e.g., AWS ECS, Render, or Railway):
- **Frontend Container:** Node.js 20 environment serving Next.js SSR and BFF route handlers.
- **Backend API Container:** Python 3.11/3.13 running Uvicorn with multiple workers behind an Application Load Balancer.
- **Database:** Managed PostgreSQL 16 instance with automated snapshots and read-replicas.
- **Background Worker:** Runs as a dedicated background worker container executing `CampaignJobWorker.run_worker_loop()` or via the FastAPI lifespan event loop.

### 15.2 Environment Separation
| Environment | Database Tenant Target | Real External Dispatch Allowed? | Purpose |
| :--- | :--- | :--- | :--- |
| **Local Dev** | Local PostgreSQL (`c0aae7f1...`) | No (Mock providers active) | Local feature development and unit testing |
| **QA Sandbox** | Cloud PostgreSQL (`c0aae7f1...`) | No (Simulated callbacks) | Automated regression QA, staging validation |
| **Production** | Cloud PostgreSQL (`0d85dc9f...`) | Yes (Guarded by channel flags) | Real-world customer outbound sales operations |

---

## 16. Current Limitations and Technical Debt

1. **Assisted Rather than Autonomous LinkedIn Dispatch:**
   - LinkedIn OpenID Connect authentication and token encryption are fully implemented.
   - However, LinkedIn's Developer API policies restrict direct cold message sending; outbound LinkedIn actions currently operate in an "assisted" queue requiring SDR manual confirmation.
2. **Poplar Physical Mail Live Sending Intentionally Guarded:**
   - Physical mail pre-flight address verification and PDF proof generation are fully implemented and verified.
   - Live postcard printing is intentionally held closed (`POPLAR_ALLOW_LIVE_SENDING=False`) to prevent unintentional print-house billing.
3. **HubSpot CRM Synchronization is Read-Only (Phase 1):**
   - The sync engine reliably pulls Contacts, Companies, and Deals from HubSpot into Agile Sales.
   - It does not yet push new deals or status updates created in Agile Sales back into HubSpot.
4. **Frontend Lacks Automated Component Test Suite:**
   - All 69 automated tests currently reside in the backend. Adding Playwright end-to-end tests for the frontend UI is recommended.
5. **Scheduler Process Coupling:**
   - The background scheduler currently runs inside the FastAPI process lifespan via an asyncio task. In high-traffic multi-instance production environments, this should be decoupled into a dedicated worker container.

---

## 17. Future Architecture Improvements

Recommended roadmap for ongoing development, prioritized by business impact:

### Priority 1: High Reliability & Distributed Worker Scalability
- **Action:** Extract `CampaignJobWorker` and `run_graph_auto_sync_loop` into independent background worker containers managed by supervisor/systemd or Docker.
- **Benefit:** Decouples background processing load from user-facing HTTP request latencies and prevents duplicate scheduler ticks across multi-instance load-balanced backend deployments.

### Priority 2: Bi-directional HubSpot CRM Synchronization
- **Action:** Implement Phase 2 of HubSpot CRM integration, adding an event listener that pushes deal stage changes, lead conversions, and contact edits back to HubSpot v3 REST API.
- **Benefit:** Eliminates CRM data drift and ensures sales managers who work primarily inside HubSpot have real-time visibility into Agile Sales progress.

### Priority 3: Automated Frontend E2E Testing (Playwright)
- **Action:** Introduce a Playwright test suite in `frontend/tests/` covering core sales flows (Lead conversion drawer, Kanban deal drag-and-drop, CSV import modal).
- **Benefit:** Catches UI regressions, hydration errors, and client-side state bugs before staging deployment.

### Priority 4: Real-Time WebSocket Notifications for Live Voice SDR Calls
- **Action:** Add a FastAPI WebSocket endpoint streaming Retell call events to the Sales Dashboard in real time.
- **Benefit:** SDRs can observe live conversational AI phone calls as they occur, seeing transcripts streamed line-by-line and receiving instant notifications when an AI agent books a meeting.

---

## 18. Glossary

| Term | Technical / Business Definition |
| :--- | :--- |
| **SDR** | Sales Development Representative; sales rep focused on outbound prospecting and qualification. |
| **Lead** | A prospective business or contact that has not yet been verified or converted into an active CRM contact. |
| **Contact** | A verified person belonging to a Company in the CRM, eligible for multi-channel sales cadences. |
| **Company** | An account-level organization in the CRM, associated with contacts and deals. |
| **Deal** | A qualified revenue opportunity with a monetary value, close date, and specific stage within a pipeline. |
| **Pipeline Stage** | A sequential phase in the sales cycle (e.g., *Meeting Scheduled*, *Proposal Sent*) with an assigned win probability percentage. |
| **Cadence / Campaign** | A structured, multi-step, multi-day sales outreach sequence combining Email, AI Voice SDR calls, and SMS. |
| **CampaignContact** | An enrollment join record connecting a Contact to a Campaign, tracking their current step and execution status. |
| **SELECT ... FOR UPDATE SKIP LOCKED** | PostgreSQL locking mechanism that allows concurrent workers to claim unassigned jobs without blocking or colliding. |
| **Lease Fencing Token** | A unique UUID attached to a job during worker claiming to ensure expired or crashed workers cannot overwrite valid job states. |
| **Retell AI** | Conversational voice AI platform powering autonomous inbound and outbound SDR phone agents. |
| **BFF (Backend-For-Frontend)** | Architectural pattern where Next.js API route handlers proxy requests from the browser to the FastAPI backend. |
| **QA Sandbox** | Dedicated tenant organization (`c0aae7f1-95bb-485f-bb9b-e3ed95469912`) safely isolated for automated and exploratory tests. |
| **Entitlement** | Commercial permission grant controlling tenant access to communication channels (SMS, Voice, Physical Mail). |
| **Overdue Staleness Gate** | Safeguard placing cadence steps delayed >24 hours into `held` status for manual SDR approval. |

---

## 19. Important File and Directory Reference

| Module | Important File / Directory | Responsibility |
| :--- | :--- | :--- |
| **Core Backend** | `backend/app/main.py` | FastAPI application initialization, CORS middleware, lifespan background loops |
| **Configuration** | `backend/app/core/config.py` | Pydantic settings, environment variables, fail-closed feature flags |
| **Security** | `backend/app/core/security.py` | Argon2id password hashing, JWT token creation, signing, and verification |
| **API Deps** | `backend/app/api/deps.py` | Dependency injection: `get_db`, `get_current_user`, `get_current_organization` |
| **QA Safeguards**| `backend/app/core/qa_safeguard.py` | Production tenant mutation guards, QA Sandbox resolution |
| **Test Detection**| `backend/app/core/test_detection.py` | Automated synthetic/test data classification (`classify_is_test`) |
| **Lead Routes** | `backend/app/api/v1/leads.py` | Lead CRUD, CSV batch import, qualification, routing, CRM conversion |
| **Lead Service**| `backend/app/services/lead_generation/service.py` | Lead business logic, scoring, deduplication, `convert_lead_to_crm` |
| **Lead Routing**| `backend/app/services/lead_qualification/routing_service.py` | Evaluates priority routing rules and assigns leads to sales reps |
| **CRM Models**  | `backend/app/models/crm.py` | SQLAlchemy models for `Company`, `Contact`, `Deal`, `Pipeline`, `PipelineStage` |
| **Deal Service**| `backend/app/services/deal_service.py` | Deal validation, pipeline stage movements, win/loss status handling |
| **Job Queue**   | `backend/app/models/campaign_execution_job.py` | Persistent queue model (`a1b2c3d4e5f7`), statuses, lease fields |
| **Job Service** | `backend/app/services/campaign_execution/job_service.py` | Enqueuing step jobs, atomic locking (`SKIP LOCKED`), lease recovery |
| **Worker**      | `backend/app/services/campaign_execution/worker.py` | Asynchronous worker daemon, provider dispatch, lease heartbeats |
| **Scheduler**   | `backend/app/services/campaign_scheduler.py` | Multi-step sequence advancement, overdue staleness gate |
| **Voice Service**| `backend/app/services/outreach/voice_followup.py` | Retell webhook HMAC verification, outcome extraction, follow-up emails |
| **Voice Client**| `backend/app/services/voice/retell_client.py` | Retell API communication client for outbound call initiation |
| **SMS Service** | `backend/app/services/sms/service.py` | Twilio SMS dispatch, phone normalization, opt-out suppression |
| **Graph Sync**  | `backend/app/services/graph/sync_service.py` | Microsoft Graph delta sync, support email ingestion & contact matching |
| **HubSpot Sync**| `backend/app/services/integrations/hubspot/sync.py` | Read-only HubSpot CRM synchronization of contacts, companies, deals |
| **Entitlements**| `backend/app/services/entitlements_service.py` | Channel tier governance, upgrade request workflow and approval |
| **Analytics**   | `backend/app/services/analytics_service.py` | Real operational KPI metrics for leads, deals, outreach, and voice calls |
| **Frontend Shell**| `frontend/src/components/layout/app-shell.tsx` | Main application shell, top bar, dynamic navigation |
| **Sidebar**     | `frontend/src/components/layout/sidebar.tsx` | Sales navigation items, mode switcher, badge displays |
| **App Mode**    | `frontend/src/contexts/AppModeContext.tsx` | Enforces Sales vs Marketing mode isolation based on user access levels |
| **Sales Dash**  | `frontend/src/app/sales/page.tsx` | Executive Sales Dashboard rendering KPIs and recent CRM leads |
| **Lead UI**     | `frontend/src/app/sales/leads/page.tsx` | Lead management interface, CSV importer, bulk actions |
| **Lead Drawer** | `frontend/src/components/leads/lead-detail-drawer.tsx` | Detailed prospect inspection, qualification notes, conversion trigger |
| **Pipeline UI** | `frontend/src/app/sales/pipeline/page.tsx` | Kanban deal board, pipeline metrics, stage progression |
| **Inbox UI**    | `frontend/src/app/inbox/page.tsx` | Support mailbox triage, message matching, review status actions |
| **Integrations**| `frontend/src/app/sales/integrations/page.tsx` | HubSpot, Retell, Twilio, Poplar status and control dashboard |
| **BFF Proxy**   | `frontend/src/app/api/` | Secure Next.js proxy route handlers forwarding client requests to FastAPI |
