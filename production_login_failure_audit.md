# Production Login Failure Audit Report

**Date of Investigation:** November 5, 2026  
**Investigated Systems:** Agile Sales & Marketing Platform  
**Target AWS Account:** `575850124498` (`agile-receivables`)  
**AWS Region:** `us-east-2`  
**Classification:** Read-Only Technical Audit  

---

## 1. Executive Summary

When attempting to log in to the live production application deployed on AWS Amplify (`https://main.d2mlvo6ysgyf2b.amplifyapp.com/login`), the application immediately returns **"Service Unavailable"** (HTTP 503).

A thorough, read-only investigation across the Next.js frontend, AWS Amplify Web Compute, AWS API Gateway, and backend EC2 infrastructure identified two compounding root causes:

1. **Stale Target IP in API Gateway HTTP Proxy Integration:**  
   The HTTP API Gateway (`2wy39hqdrc`, `agile-sales-api-development`) is hardcoded to reverse-proxy all incoming requests to `http://18.118.146.163:8000/`. The backend EC2 instance (`i-0104a7d71d82157f2`) does not possess an Elastic IP (EIP) and was rebooted on `2026-11-05 09:45:43 UTC`. Upon reboot, AWS dynamically assigned it a new public IP (`3.15.148.10`), abandoning `18.118.146.163`. As a result, API Gateway attempts to forward requests to an unroutable IP and returns HTTP 503 `{"message":"Service Unavailable"}`.

2. **Backend Service Inactive on EC2 Host (Missing Boot Autostart):**  
   Even if traffic were routed to the instance's new IP, the FastAPI backend Docker container (`agile-sales-backend`) on instance `i-0104a7d71d82157f2` is **stopped** (`Exited (0) 16 hours ago`). The systemd unit file `/etc/systemd/system/agile-sales-backend.service` created during instance bootstrap was left in a `disabled` state (never enabled with `systemctl enable`). When the host rebooted, the backend process was not restarted. Port 8000 is completely closed.

---

## 2. Confirmed Application Architecture

```
[ Client Browser ]
        │  POST /api/auth/login
        ▼
[ AWS Amplify Hosting (Web Compute) ]
  • App ID: d2mlvo6ysgyf2b (main branch)
  • Next.js App Router BFF Proxy: src/app/api/auth/login/route.ts
  • Reads BACKEND_URL: https://2wy39hqdrc.execute-api.us-east-2.amazonaws.com
        │
        │  POST /api/v1/auth/login (HTTPS)
        ▼
[ AWS API Gateway (HTTP API v2) ]
  • API ID: 2wy39hqdrc (Name: agile-sales-api-development)
  • Route: ANY /{proxy+} -> Integration 7bq6a0g (HTTP_PROXY)
  • Target URI: http://18.118.146.163:8000/{proxy}   <-- [FAILURE: STALE IP]
        │
        │  (Connection Timed Out / Dropped)
        ▼
[ AWS EC2 Backend Host ]
  • Instance ID: i-0104a7d71d82157f2 (agile-sales-marketing-development-backend)
  • Launch Time: 2026-11-05 09:45:43 UTC
  • Current Public IP: 3.15.148.10 (Old IP: 18.118.146.163)
  • Private IP: 10.2.1.18 (VPC: vpc-0a896659fe7bea154)
  • Backend Container: agile-sales-backend (Exited 0, inactive) <-- [FAILURE: PROCESS DOWN]
  • Systemd Unit: agile-sales-backend.service (disabled, dead)
        │
        ▼
[ Database Layer ]
  • Engine: PostgreSQL 16
  • Target: AWS RDS (agile-receivables-development / agile-receivables-production)
```

---

## 3. Frontend Deployment Details

| Attribute | Value | Verification Source |
| :--- | :--- | :--- |
| **Amplify App ID** | `d2mlvo6ysgyf2b` | `aws amplify list-apps` |
| **App Name** | `frontend` | AWS Amplify Console / CLI |
| **Repository** | `https://github.com/Agile-S-M/frontend` | Amplify App Configuration |
| **Production Branch** | `main` | `aws amplify list-branches` |
| **Hosting Platform** | `WEB_COMPUTE` (Next.js SSR) | Amplify App Spec |
| **Live Domain** | `https://main.d2mlvo6ysgyf2b.amplifyapp.com` | Verified HTTP 200/307 |
| **Latest Build Job** | Job #4 (Status: `SUCCEED`) | `aws amplify list-jobs` |
| **Latest Commit** | `a38aebadc092c28ffc603296056b235ee4ce52b2` | Commit: `fix(auth): fallback getBackendUrl to NEXT_PUBLIC_API_URL` |
| **Frontend Framework** | Next.js 15.0.0 / React 19 / TypeScript / Tailwind | `package.json` |

### Environment Variables Configured on Amplify:
*Values kept redacted in accordance with safety policies; only key names and endpoint targets evaluated:*
- `BACKEND_URL`: `https://2wy39hqdrc.execute-api.us-east-2.amazonaws.com`
- `NEXT_PUBLIC_API_URL`: `https://2wy39hqdrc.execute-api.us-east-2.amazonaws.com`
- `NEXT_PUBLIC_APP_ENV`: `development`

---

## 4. Backend Hosting Details

| Attribute | Value | Verification Source |
| :--- | :--- | :--- |
| **Compute Type** | AWS EC2 (Instance: `i-0104a7d71d82157f2`, `t3.micro`) | `aws ec2 describe-instances` |
| **Instance Name Tag** | `agile-sales-marketing-development-backend` | EC2 Tags |
| **Project Tag** | `agile-sales-marketing` | EC2 Tags |
| **Current Public IP** | `3.15.148.10` | EC2 Network Interfaces |
| **Private IP** | `10.2.1.18` (Subnet: `subnet-086ed513a93b874a5`) | EC2 Network Interfaces |
| **Elastic IP Assigned?** | **No** (Dynamic Public IPv4) | `Association.IpOwnerId: amazon` |
| **Container Engine** | Docker on Amazon Linux 2023 | EC2 User Data / SSM |
| **Container Image** | `575850124498.dkr.ecr.us-east-2.amazonaws.com/agile-sales-marketing-backend:latest` | `docker images` |
| **Reverse Proxy API Gateway** | `2wy39hqdrc` (`agile-sales-api-development`) | `aws apigatewayv2 get-apis` |
| **Target Integration URI** | `http://18.118.146.163:8000/` and `http://18.118.146.163:8000/{proxy}` | `aws apigatewayv2 get-integrations` |
| **Database** | Amazon RDS PostgreSQL 16 | `aws rds describe-db-instances` |
| **Secrets Management** | AWS Secrets Manager (`agile-sales-marketing-development-app-secrets`) | `aws secretsmanager list-secrets` |

---

## 5. Login Request Flow & Failure Trace

### Step 1: User Submission
User navigates to `https://main.d2mlvo6ysgyf2b.amplifyapp.com/login` and enters credentials. The client component `LoginForm` (`frontend/src/app/(auth)/login/page.tsx`) intercepts the form submit:
```typescript
const response = await fetch("/api/auth/login", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
});
```

### Step 2: Next.js BFF Handler Execution
Next.js SSR Route Handler (`frontend/src/app/api/auth/login/route.ts`) resolves `backendUrl`:
```typescript
const backendUrl = getBackendUrl(); // Resolves to process.env.BACKEND_URL -> https://2wy39hqdrc.execute-api.us-east-2.amazonaws.com
const response = await fetch(`${backendUrl}/api/v1/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, password }),
  cache: "no-store",
});
```

### Step 3: API Gateway Forwarding
The HTTPS request lands on API Gateway `2wy39hqdrc`.
Integration `7bq6a0g` maps this route to:
```
http://18.118.146.163:8000/api/v1/auth/login
```
Because `18.118.146.163` was released upon EC2 restart, the IP is unreachable. After the gateway timeout threshold (~3,000 ms), API Gateway terminates the connection and returns:
- **HTTP Status:** `503 Service Unavailable`
- **Response Payload:** `{"message":"Service Unavailable"}`

### Step 4: Next.js Response Relay
The Next.js route handler receives the 503 response from API Gateway. Because `fetch()` completed (HTTP 503 is a valid response, not a thrown socket exception), `handleBackendProxyError()` is bypassed:
```typescript
const data = await response.json().catch(() => ({}));
if (!response.ok) {
  return NextResponse.json(data, { status: response.status }); // Returns 503 {"message":"Service Unavailable"}
}
```

### Step 5: UI Presentation
In `login/page.tsx`:
```typescript
const errorDetail =
  data?.detail ||
  data?.error ||
  data?.message ||
  "Authentication failed. Please verify your credentials.";
setErrorMessage(errorDetail); // Displays "Service Unavailable" in the red alert box
```

---

## 6. Actual Failing Components & Evidence

### Evidence A: Direct Verification of API Gateway Endpoint
Testing the API Gateway directly confirms it returns HTTP 503 regardless of the frontend:
```powershell
Invoke-RestMethod -Uri "https://2wy39hqdrc.execute-api.us-east-2.amazonaws.com/health"
# Result: 503 Service Unavailable -> {"message":"Service Unavailable"}
```

### Evidence B: IP Address Drift on EC2 Instance
Inspecting EC2 instance `i-0104a7d71d82157f2` shows:
- **Instance State:** `running`
- **Launch Time:** `2026-11-05 09:45:43 UTC`
- **Current Public IP:** `3.15.148.10`
- **Previous Public IP:** `18.118.146.163` (recorded in API Gateway Terraform integration on Nov 4)
- **Elastic IP (EIP):** None attached.

### Evidence C: Backend Process State on EC2
Diagnostic inspection via AWS Systems Manager (SSM) revealed:
```bash
# docker ps -a
CONTAINER ID   IMAGE                        COMMAND                  STATUS
2a91afa1a2dd   agile-sales-backend:latest   "uvicorn app.main:ap…"   Exited (0) 16 hours ago

# ss -tulpn
# Port 8000 is NOT listening. Only port 22 (sshd) and 42179 (containerd) are active.

# systemctl status agile-sales-backend
agile-sales-backend.service - Agile Sales and Marketing FastAPI Backend Container
   Loaded: loaded (/etc/systemd/system/agile-sales-backend.service; disabled; preset: disabled)
   Active: inactive (dead)
```

Docker logs confirm the application was healthy prior to host shutdown:
```
INFO: 127.0.0.1:48526 - "GET /health HTTP/1.1" 200 OK
INFO: Shutting down
agile_sales_marketing: Shutting down background campaign scheduler cleanly...
INFO: Application shutdown complete.
INFO: Finished server process [1]
```
The container exited cleanly (code 0) when the instance was stopped yesterday. Upon reboot, the systemd service remained `disabled` and never restarted the container.

---

## 7. Root Cause Analysis

The failure is caused by a two-stage infrastructure gap:

1. **Brittle Public IP Binding:**  
   The HTTP API Gateway uses a raw public IP (`http://18.118.146.163:8000/`) rather than an Elastic IP, an Application Load Balancer, or a private VPC Link. Because the EC2 instance has a dynamic IP, the first reboot broke all ingress traffic.

2. **Incomplete Host Bootstrap Automation:**  
   In the EC2 instance User Data script, the systemd unit `/etc/systemd/system/agile-sales-backend.service` was created and loaded into memory (`systemctl daemon-reload`), but was never enabled with `systemctl enable`. On instance boot, systemd ignored the unit, leaving the backend container stopped.

---

## 8. Other Potential Contributing Issues

1. **Environment Configuration Ambiguity:**  
   Amplify environment variables specify `NEXT_PUBLIC_APP_ENV="development"`, and `BACKEND_URL` points to `agile-sales-api-development`. If this environment is intended to be the final production instance, the environment naming and underlying resources should be promoted or aligned to production standards.
2. **Plaintext HTTP on Backend Ingress:**  
   The API Gateway currently proxies to the EC2 backend over unencrypted HTTP across the public Internet (`http://18.118.146.163:8000`). For a production deployment, traffic between API Gateway and EC2 should either pass through a private VPC Link (keeping traffic inside the AWS private network) or terminate HTTPS with a TLS certificate.
3. **Absence of Container Healthcheck / Auto-Recovery:**  
   Without an Auto Scaling Group, ECS task definition, or persistent systemd service, any transient OOM or process failure on the `t3.micro` instance leaves the entire platform offline.

---

## 9. Recommended Fix (Awaiting User Approval)

The following sequence of actions will permanently resolve the issue without disrupting existing configurations:

### Phase A: Restore EC2 Backend Container & Enable Autostart
1. Start and enable the systemd unit on EC2 instance `i-0104a7d71d82157f2`:
   ```bash
   sudo systemctl enable --now agile-sales-backend.service
   ```
2. Verify container startup and local health:
   ```bash
   curl http://127.0.0.1:8000/health
   ```

### Phase B: Fix IP Drift & Stabilize Gateway Routing
Choose one of the following two architectural approaches:
- **Option 1 (Immediate / Minimal Change):**
  1. Allocate an **Elastic IP (EIP)** and associate it with EC2 instance `i-0104a7d71d82157f2`.
  2. Update the API Gateway `2wy39hqdrc` integrations (`7bq6a0g` and `hncdqc6`) with the new Elastic IP URI:
     `http://<NEW_ELASTIC_IP>:8000/{proxy}` and `http://<NEW_ELASTIC_IP>:8000/`.
- **Option 2 (Production Best Practice - Recommended):**
  1. Configure an API Gateway **VPC Link** for HTTP API `2wy39hqdrc`.
  2. Route traffic securely to the instance's private IP (`10.2.1.18:8000`) within `vpc-0a896659fe7bea154`. This eliminates public IP exposure and survives IP reallocations.

### Phase C: Verify Full Production Login
1. Verify `GET https://2wy39hqdrc.execute-api.us-east-2.amazonaws.com/health` returns `200 OK`.
2. Verify `POST https://main.d2mlvo6ysgyf2b.amplifyapp.com/api/auth/login` returns valid session cookies and user details.
3. Perform a login test in the live browser.

---

## 10. Exact Files and AWS Configurations Requiring Attention

| Component | Identifier / Path | Required Change |
| :--- | :--- | :--- |
| **EC2 Systemd Service** | Instance `i-0104a7d71d82157f2` (`/etc/systemd/system/agile-sales-backend.service`) | Run `systemctl enable --now agile-sales-backend` |
| **EC2 Bootstrap / Terraform** | Terraform User Data template for EC2 backend | Add `systemctl enable --now agile-sales-backend` |
| **EC2 Networking** | Instance `i-0104a7d71d82157f2` Network Interface | Allocate and associate an Elastic IP (EIP) |
| **API Gateway Integrations** | API `2wy39hqdrc`, Integrations `7bq6a0g` & `hncdqc6` | Update `IntegrationUri` from `http://18.118.146.163:8000/` to current Elastic IP (or VPC Link) |
| **Amplify Environment Variables** | App `d2mlvo6ysgyf2b` (`frontend`) | Confirm whether `NEXT_PUBLIC_APP_ENV` should remain `development` or be switched to `production` |
