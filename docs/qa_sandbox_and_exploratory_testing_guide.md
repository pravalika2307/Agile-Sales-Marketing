# QA Sandbox & Exploratory Testing Guide

**Target Audience:** Engineers, QA Specialists, and Automated Script Authors  
**Applies to:** `D:\Agile-Sales-Marketing`  
**Last Updated:** November 2026  

---

## 1. Golden Rules of Tenant Isolation

1. **OPERATIONAL PRODUCTION TENANT IS STRICTLY READ-ONLY FOR SCRIPTS:**
   * **Organization Name:** Agile Sales & Marketing
   * **Organization ID:** `0d85dc9f-1520-4bcb-8af4-8aad025255cb`
   * **Organization Slug:** `agile-sales-marketing-org`
   * **Rule:** Exploratory test scripts, scratch scripts, fixture generators, and simulated webhook calls must **NEVER** write or insert records into this tenant.

2. **DEDICATED QA SANDBOX TENANT FOR EXPLORATORY TESTING:**
   * **Organization Name:** Agile QA Sandbox
   * **Organization ID:** `c0aae7f1-95bb-485f-bb9b-e3ed95469912`
   * **Organization Slug:** `agile-qa-sandbox-org` (legacy alias: `e2e-testing-org`)
   * **Dedicated Sandbox User:** `e2e_lists@example.com` (password: `Password123!`)
   * **Rule:** All experimental campaigns, simulated webhook events, mock contacts, and direct ORM exploratory test scripts must target this organization.

3. **FAIL-CLOSED ENFORCEMENT:**
   * Any script that attempts to write records into `0d85dc9f-1520-4bcb-8af4-8aad025255cb` without an explicit administrative override (`ALLOW_PRODUCTION_CRM_MUTATION=true`) will abort immediately with `ProductionDataProtectionError`.
   * Never write scripts using `db.query(Organization).first()`. Always use the safe resolver helpers.

---

## 2. How to Target the QA Sandbox in Scripts

### 2.1 Using the Centralized Safeguard Helper (Recommended)

Import the safe resolver from [`app.core.qa_safeguard`](file:///D:/Agile-Sales-Marketing/backend/app/core/qa_safeguard.py):

```python
import sys
sys.path.insert(0, "backend")

from app.core.database import SessionLocal
from app.core.qa_safeguard import (
    get_qa_organization,
    resolve_script_target_organization,
    install_production_mutation_guard,
    QA_SANDBOX_ORG_ID,
)
from app.models.lead import Lead

def run_exploratory_test():
    db = SessionLocal()
    try:
        # Install the session-level write guard (aborts any flush targeting production)
        install_production_mutation_guard(db)

        # Retrieve the safe QA Sandbox Organization
        qa_org = get_qa_organization(db)
        print(f"Executing in safe test organization: {qa_org.name} ({qa_org.id})")

        # Safely insert or query records
        test_lead = Lead(
            organization_id=qa_org.id,
            company_name="Exploratory Prospect",
            email="test_prospect@agiletesting.local",
            is_test=True,
        )
        db.add(test_lead)
        db.commit()
        print(f"Lead created successfully in QA Sandbox: {test_lead.id}")

    finally:
        db.close()

if __name__ == "__main__":
    run_exploratory_test()
```

---

### 2.2 Using Environment Variables

You can instruct scripts to target a specific tenant using standard environment variables:

```powershell
$env:TARGET_ORGANIZATION_SLUG="agile-qa-sandbox-org"
python my_scratch_script.py
```

Inside the script:
```python
from app.core.qa_safeguard import resolve_script_target_organization

# Automatically reads $env:TARGET_ORGANIZATION_SLUG or $env:TARGET_ORGANIZATION_ID
# Fails closed if the environment variable points to production!
target_org = resolve_script_target_organization(db)
```

---

### 2.3 Authenticating as the QA Sandbox User via REST API

For end-to-end API tests or frontend development:

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "e2e_lists@example.com",
  "password": "Password123!"
}
```

The returned JWT token will be strictly tenant-scoped to `c0aae7f1-95bb-485f-bb9b-e3ed95469912`. All leads, contacts, campaigns, and metrics created under this token will remain completely isolated from the operational CRM.

---

## 3. Data Integrity & Ingestion Rules

When inserting leads or contacts in the QA Sandbox:
1. Always mark test records with `is_test = True`.
2. Even if `is_test` is omitted, the centralized detection engine in [`app.core.test_detection`](file:///D:/Agile-Sales-Marketing/backend/app/core/test_detection.py) will automatically classify records matching test domains (`@blackmesa.org`, `@testacme.com`, `@agiletesting.local`, `.example.com`), test prefixes (`csvtest_*`), and test names.
3. Operational CRM views and KPI queries in production apply `exclude_test = True` and strict tenant boundaries, guaranteeing that QA sandbox data never surfaces in client dashboards.
