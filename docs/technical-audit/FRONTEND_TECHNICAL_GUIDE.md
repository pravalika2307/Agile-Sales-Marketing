# Frontend Technical Guide & Architecture

**Platform:** Agile Sales & Marketing  
**Frontend Location:** `D:\Agile-Sales-Marketing\frontend`  
**Audit Date:** October 2026  
**Auditor Roles:** Senior Full-Stack Engineer, Frontend Specialist  

---

## 1. Technology Stack & Dependencies

The frontend application is built on the modern React and Next.js ecosystem:

| Package | Version | Purpose |
| :--- | :--- | :--- |
| **Next.js** | `16.4.0` | App Router framework, server routing, and BFF route handlers. |
| **React** | `19.3.0` | Component lifecycle, hooks, and UI rendering. |
| **React DOM** | `19.3.0` | DOM rendering and portal mounting. |
| **TypeScript** | `^5` | Strict static typing and interface contracts. |
| **Tailwind CSS** | `^3.4.17` | Utility-first styling with custom palette and dark-mode support. |
| **Lucide React** | `^1.53.0` | Modern, consistent iconography across all pages and buttons. |
| **clsx / tailwind-merge** | `2.1.1 / 3.7.0` | Dynamic className composition and utility merging. |

---

## 2. Directory Structure

```
frontend/
├── public/                 # Static assets and icons
├── src/
│   ├── app/                # Next.js App Router pages and API routes
│   │   ├── analytics/      # Analytics page (/analytics)
│   │   ├── api/            # Next.js proxy route handlers (/api/...)
│   │   │   ├── campaigns/  # Campaign proxy endpoints
│   │   │   ├── contacts/   # Contact proxy endpoints
│   │   │   ├── leads/      # Lead proxy endpoints
│   │   │   ├── outreach/   # Outreach proxy endpoints
│   │   │   └── integrations/# HubSpot proxy endpoints
│   │   ├── campaigns/      # Campaigns page (/campaigns)
│   │   ├── companies/      # Companies catalog (/companies)
│   │   ├── find-leads/     # Prospecting search (/find-leads)
│   │   ├── integrations/   # Integration status (/integrations)
│   │   ├── leads/          # Leads page (/leads)
│   │   ├── outreach/       # Outreach page (/outreach)
│   │   ├── pipeline/       # Pipeline board (/pipeline)
│   │   ├── layout.tsx      # Root HTML layout and fonts
│   │   └── page.tsx        # Dashboard home page (/)
│   ├── components/         # Reusable UI component library
│   │   ├── campaigns/      # Campaign detail drawer, sequence builder
│   │   ├── charts/         # Bar charts, line charts, chart cards
│   │   ├── layout/         # AppShell, Sidebar, Header
│   │   ├── leads/          # Lead detail drawer, modals
│   │   ├── outreach/       # Outreach table and drawer
│   │   ├── pipeline/       # Deal cards, stages
│   │   └── ui/             # Buttons, inputs, modals, badges, cards
│   ├── lib/                # Utility helpers (utils.ts)
│   └── services/           # Typed client-side API services
│       ├── analyticsService.ts
│       ├── campaignService.ts
│       ├── companyService.ts
│       ├── crmLeadService.ts
│       ├── hubspotService.ts
│       ├── leadQualificationService.ts
│       ├── leadService.ts
│       ├── outreachService.ts
│       └── pipelineService.ts
├── package.json
├── tailwind.config.ts
└── tsconfig.json
```

---

## 3. Reusable UI Components & Design System

The application uses a curated component system located in `frontend/src/components/ui`:

1. **`AppShell` (`components/layout/app-shell.tsx`):**
   * Encapsulates the global navigation drawer, collapsible sidebar, header with organization switcher, and content container.
2. **`Modal` (`components/ui/modal.tsx`):**
   * Accessible dialog component mounted via React portals, with background overlay, keyboard ESC dismissal, and focus trapping.
3. **`Drawer` (`components/ui/drawer.tsx`):**
   * Sliding right-hand drawer used for detailed record inspection without leaving the active table view (used in Leads, Campaigns, and Companies).
4. **`KpiCard` (`components/ui/kpi-card.tsx`):**
   * Standardized dashboard metric tile showing KPI title, current value, secondary comparison, icon, and status indicator.
5. **`Button` (`components/ui/button.tsx`):**
   * Supports variants: `primary`, `secondary`, `destructive`, `outline`, `ghost`, and sizes: `sm`, `md`, `lg`. Supports inline loading spinners (`isLoading`).
6. **`Badge` (`components/ui/badge.tsx`):**
   * Colored pill indicator for statuses (`new`, `qualified`, `active`, `sent`, `hot`, `cold`).

---

## 4. State Management & Data-Fetching Patterns

* **Component-Level Reactive State:**
  * Uses native React hooks (`useState`, `useEffect`, `useCallback`, `useMemo`).
  * Avoids heavy external state stores (like Redux) in favor of localized, predictable state lifecycles.
* **Data-Fetching Pattern:**
  * On mount (`useEffect`), pages trigger typed service functions (e.g. `fetchCRMLeads()`, `fetchCampaigns()`).
  * Responses are unpacked into typed state arrays, updating loading and error states.
* **Safe List Refresh Pattern:**
  * When a destructive or mutative action occurs (e.g. `deleteLead()`, `deleteCampaign()`), the table state is refreshed cleanly:
  ```typescript
  // Example from leads/page.tsx
  const handleConfirmDelete = async () => {
    if (!leadToDelete) return;
    setIsDeleting(true);
    try {
      await deleteLead(leadToDelete.id);
      setDeleteSuccessMessage(`Lead "${leadToDelete.firstName} ${leadToDelete.lastName}" deleted.`);
      setLeadToDelete(null);
      await loadLeads(); // Re-fetches current search & pagination state
    } catch (err) {
      setDeleteError("Failed to delete lead. Please try again.");
    } finally {
      setIsDeleting(false);
    }
  };
  ```

---

## 5. Campaign Sequence Builder & Live Contact Preview

Located in `frontend/src/components/campaigns/campaign-detail-drawer.tsx`:

1. **Sequential Step Management:**
   * Sequences display steps ordered by `step_number`.
   * Each step configures `delay_days`, `delay_hours`, `subject_template`, and `body_template`.
2. **Live Contact Preview Engine:**
   * When editing a step, users can select any enrolled contact from the **Live Contact Preview** dropdown.
   * The frontend calls `POST /api/v1/campaigns/{id}/steps/{step_id}/preview` passing the target `contact_id`.
   * The backend renders tokens (`{{contact.first_name}}`, `{{company.name}}`, etc.) and returns the rendered subject and body.
   * The drawer displays the resolved email in an interactive preview card, highlighting any unreplaced tokens.

---

## 6. Form Validation & Error Handling

* **Client Validation:**
  * Email inputs validate against standard regex patterns before submitting.
  * Required fields (First Name, Last Name, Company Name) enforce non-empty strings.
* **Destructive Action Safeguards:**
  * Single-click destructive actions are strictly prevented.
  * All deletions (Lead, Campaign, Contact Removal) require an interactive confirmation modal showing record details (Name, Email, Enrolled count).
  * Submission buttons disable and display loading spinners during active HTTP requests.
* **Inline Error Displays:**
  * Failed network calls render contextual red alert banners (`alert-destructive`) rather than unhandled browser popups.

---

## 7. Frontend Verification & Quality Checks

* **TypeScript Compilation:**
  * Checked using `npx tsc --noEmit`.
  * **Result:** Exited 0 with zero type errors across the entire codebase.
* **Known Frontend Limitations:**
  * User authentication session is not yet tied to a login/logout form (Next.js route handlers currently pass a default organization header).
  * CSV upload modal currently lacks a client-side CSV column mapping and preview grid.
