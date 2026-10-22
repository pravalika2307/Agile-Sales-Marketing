# AWS Infrastructure & Deployment Feasibility Analysis Report

**Target Project:** Agile Sales & Marketing Platform  
**Target Region:** AWS `us-east-2` (US East - Ohio)  
**AWS Account ID:** `575850124498`  
**IAM Identity:** `arn:aws:iam::575850124498:user/lakshay-narula`  
**Date of Audit:** October 23, 2026  
**Auditor:** Senior Cloud & DevOps Infrastructure Architect  
**Classification:** Internal Management & Architecture Review  

---

## 1. Executive Summary

This report delivers a comprehensive, evidence-based assessment of the current AWS cloud infrastructure for the **Agile Sales & Marketing** initiative. The platform expands Agile Receivables from its legacy marketing automation scripts into an enterprise-grade SaaS application featuring:

1. **Next.js 16 App Router Frontend**: Interactive marketing campaign creation wizard, drag-and-drop brand knowledge ingestion (PDF, DOCX, CSV parsing via `pdf-parse` and `papaparse`), AI training loop controls, and multi-platform analytics dashboards (Instagram, Facebook, LinkedIn, X).
2. **High-Throughput Webhook Ingestion Engine**: `/api/webhooks/n8n/social-analytics`, which ingests batch JSON payloads containing dozens of historical and live social media posts, executing atomic multi-table upserts (`Post` and `PostAnalytics`) via Prisma ORM interactive transactions (`$transaction`).
3. **FastAPI Backend & Voice Outbound Service**: Python FastAPI service running background scheduling loops (`CampaignSchedulerService`), Retell AI voice agent integration, and bidirectional HubSpot CRM synchronization.
4. **n8n Workflow Automation**: Autonomous content generation, post publishing, and analytics extraction workflows.

### Core Strategic Question
> **Can the existing AWS "development" EC2 instance be reused to host this new workload without compromising existing services or encountering out-of-memory crashes?**

### Definitive Finding & Verdict
* **Verdict:** **NOT RECOMMENDED TO REUSE IN CURRENT SPECIFICATION.**
* **Key Evidence:**
  - The designated development compute worker (`agile-receivables-development-worker`, `t3.micro` / 1 vCPU, 1 GB RAM) is currently **terminated** and scaled to zero (`Desired: 0`, `Min: 0`) in Auto Scaling Group `agile-receivables-development-worker-20260411072607827100000003`. Historical CloudWatch data reveals CPU saturation reaching **99.93%**.
  - The only running development EC2 instance is `agile-receivables-development-nat-instance` (`i-0a5450eadfdfc5372`, `t3.nano` / 0.5 GB RAM), which is a dedicated network router and cannot host application software.
  - Next.js 16 SSR and Prisma Client require a minimum of **1.0 to 1.5 GB RAM** at runtime and **>2 GB RAM** during build phases (`next build`). Co-locating n8n (minimum 500 MB – 1 GB) and the Next.js runtime on a `t3.micro` instance will trigger the Linux Kernel Out-Of-Memory (OOM) Killer, aborting active transactions.
  - The existing development RDS database (`agile-receivables-development`, `db.t3.micro`) has dangerously low free memory: average freeable memory is **~78 MB**, with troughs as low as **26 MB** (>97% memory saturation). Directing additional Prisma connection pools to it risks database downtime.

### Recommended Path Forward
Adopt a **Decoupled Serverless & Container Hybrid Architecture**:
- **Frontend**: Deploy to **AWS Amplify (WEB_COMPUTE)** using standard CI/CD connected to the Git repository. Amplify natively provides `STANDARD_8GB` build environments, automatic SSL, CDN caching, and serverless Next.js App Router compute.
- **Backend / n8n Webhook Host**: Deploy a dedicated **EC2 `t3.medium`** instance (2 vCPUs, 4 GB RAM, $30.37/mo) running Docker Compose for the FastAPI service and n8n webhook runner.
- **Database**: Isolate marketing tables in a dedicated logical database (`agile_sales_marketing`) hosted on either the underutilized **`db-dev-9`** (`db.t3.small`, 1.15 GB free RAM) or the production RDS instance (`agile-receivables-production`, `db.t3.medium`), avoiding memory contention on the overburdened `db.t3.micro`.
- **Total Projected Incremental Cost**: **~$38.00 – $48.00 / month**.

---

## 2. Current Infrastructure State

A complete read-only audit of all compute, database, and hosting resources in `us-east-2` was conducted via the AWS CLI.

### 2.1 EC2 Compute & Auto Scaling Inventory

| Instance ID | Name Tag | Instance Type | vCPU / RAM | State | Role / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `i-0a5450eadfdfc5372` | `agile-receivables-development-nat-instance` | `t3.nano` | 2 vCPU / 0.5 GB | **Running** | NAT Router for dev private subnets |
| `i-001c905a5e4d38088` | `agile-receivables-development-worker` | `t3.micro` | 1 vCPU / 1.0 GB | **Terminated** | Part of ASG (Desired=0, Min=0, Max=1) |
| `i-0550c79ce24486f35` | `stag-jump-ec2` | `t3.micro` | 1 vCPU / 1.0 GB | **Running** | Staging bastion / SSH jump host |
| `i-0c089efc263bcf095` | `prod-jump-ec2` | `t3.micro` | 1 vCPU / 1.0 GB | **Running** | Production bastion / SSH jump host |
| `i-008f365c301fb258e` | `PMS Server` | `t3.large` | 2 vCPU / 8.0 GB | **Running** | Internal Practice Management System |
| `i-0cd0cbd6a81e48ec8` | `agile-receivables-production-nat-instance` | `t3.small` | 2 vCPU / 2.0 GB | **Running** | NAT Router for prod private subnets |
| `i-0509e4386877a07c7` | `agile-receivables-staging-nat-instance` | `t3.nano` | 2 vCPU / 0.5 GB | **Running** | NAT Router for staging private subnets |
| `i-0b324d3557936ea74` | `agile-receivables-production-worker` | `t3.medium` | 2 vCPU / 4.0 GB | **Running** | Production application worker |
| `i-06400b775311e217c` | `agile-receivables-staging-worker` | `t3.small` | 2 vCPU / 2.0 GB | **Terminated** | Staging worker (scaled down) |

#### Auto Scaling Group Configuration
```json
{
  "AutoScalingGroupName": "agile-receivables-development-worker-20260411072607827100000003",
  "DesiredCapacity": 0,
  "MinSize": 0,
  "MaxSize": 1,
  "Instances": []
}
```
*Observation*: The development worker is intentional scaled to zero to save costs when inactive.

---

### 2.2 Relational Database Service (RDS) Inventory

All provisioned database engines are running PostgreSQL 16.13 on `gp3` storage in `us-east-2`:

| DB Identifier | Engine | Instance Class | Storage | Public | Status | Multi-AZ |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `agile-receivables-development` | PostgreSQL 16.13 | `db.t3.micro` (1 vCPU, 1 GB) | 40 GB gp3 | No | `available` | No |
| `agile-receivables-staging` | PostgreSQL 16.13 | `db.t3.micro` (1 vCPU, 1 GB) | 40 GB gp3 | No | `available` | No |
| `agile-receivables-production` | PostgreSQL 16.13 | `db.t3.medium` (2 vCPU, 4 GB) | 100 GB gp3 | No | `available` | No |
| `db-dev-9` | PostgreSQL 16.13 | `db.t3.small` (2 vCPU, 2 GB) | 100 GB gp3 | **Yes** | `available` | No |

---

### 2.3 AWS Amplify Applications Inventory

The account has three production and staging web applications deployed on AWS Amplify:

| App Name | App ID | Default Domain | Framework / Platform | Build Compute |
| :--- | :--- | :--- | :--- | :--- |
| `agile-frontend` | `d3hcv4oz4bjyez` | `d3hcv4oz4bjyez.amplifyapp.com` | Next.js (`WEB_COMPUTE` SSR) | `STANDARD_8GB` |
| `agile-landing-page` | `dsxrv8d0t7vv0` | `dsxrv8d0t7vv0.amplifyapp.com` | Static / Web | `STANDARD_8GB` |
| `agile-api-docs` | `d8n9sh5id1p2n` | `d8n9sh5id1p2n.amplifyapp.com` | Documentation | Default |

*Key Takeaway*: The organization already possesses deep operational familiarity and active CI/CD infrastructure for Next.js SSR via AWS Amplify's `WEB_COMPUTE` architecture.

---

## 3. Feasibility Analysis: Can We Reuse the Development EC2 Instance?

Management often seeks to reuse existing idle or development instances to minimize cloud expenditure. Below is the technical evaluation of this proposal.

### 3.1 Instance Specifications vs. Expected Workload Load Profile

| Workload Dimension | Existing Dev Worker (`t3.micro`) | Expected Agile Sales & Marketing Load | Feasibility Risk |
| :--- | :--- | :--- | :--- |
| **CPU Architecture** | 1 vCPU (2.5 GHz Intel Skylake / Cascade Lake) | Next.js Server Components, React 19 rendering, PDF parsing, AES/token verification | 🔴 **High**: `t3.micro` offers only 10% baseline CPU credits/hr. Build or batch load will exhaust burst credits rapidly. |
| **Physical Memory (RAM)** | **1,024 MB (1.0 GB)** total system memory | • Next.js runtime: ~350 MB – 500 MB<br>• Prisma Query Engine: ~150 MB – 250 MB<br>• n8n process: ~450 MB – 800 MB<br>• OS & Node buffers: ~250 MB | 🔴 **Severe (Critical)**: Total memory footprint = **1.2 GB – 1.8 GB**, exceeding physical RAM by 20% to 80%. |
| **Build Phase Overhead** | Node.js bundler (`next build` with Webpack/Turbopack) | Builds fail reliably when free memory is < 1.5 GB without massive swap file thrashing. | 🔴 **High**: Will stall or crash during `npm run build` deployments. |
| **Webhook Processing** | Ingestion of array of 50+ social analytics records with Date/Engagement calculations | JSON deserialization + Prisma transaction batching spikes CPU to 100% for 3–5 seconds. | 🟡 **Moderate**: Risk of 504 Gateway Timeouts from n8n. |

### 3.2 7-Day CloudWatch Telemetry Data

#### 1. Development EC2 Instances
- **`agile-receivables-development-nat-instance` (`i-0a5450eadfdfc5372`)**:
  - Average CPU: **3.01%**
  - Maximum 1-hour Peak CPU: **12.47%**
  - *Status*: Operational, but strictly a NAT instance handling routing between VPC private subnets and the Internet Gateway. It has only 0.5 GB RAM and must **never** be used for application hosting.
- **`agile-receivables-development-worker` (`i-001c905a5e4d38088`)**:
  - Peak CPU utilization prior to termination: **99.93%**.
  - Auto Scaling Group is currently set to 0 instances.

#### 2. Development RDS Database (`agile-receivables-development`)
- **Average CPU Utilization**: **11.45%** (Peaks: **52.03%**)
- **Database Connections**: Average **5.1**, Peak **47 connections**.
- **Freeable Memory**:
  - 7-Day Average: **81.8 MB** free
  - 7-Day Minimum: **26.2 MB** free (out of 1,024 MB total system RAM)
  - *Status*: The database is operating at **92% to 97.4% memory saturation**. Initiating Prisma connection pools (which default to `num_physical_cpus * 2 + 1` connections per serverless worker/node process) will exhaust PostgreSQL memory, triggering connection rejections: `FATAL: remaining connection slots are reserved for non-replication superuser connections`.

### 3.3 Clear Verdict & Technical Caveats

> ### 🛑 VERDICT: NOT RECOMMENDED
>
> Attempting to run the Next.js frontend, Prisma ORM, and n8n webhook receiver concurrently on a `t3.micro` development instance will cause:
> 1. **Immediate Out-Of-Memory (OOM) Termination**: The OS will kill either Node.js or PostgreSQL during webhook processing.
> 2. **Build Failures**: Next.js production builds will fail during compilation due to insufficient RAM.
> 3. **Database Starvation**: Pointing Prisma to `agile-receivables-development` will crash the database due to <30 MB of available buffer memory.
>
> **The Only Viable Way to Reuse Dev Worker:**  
> If the development Auto Scaling Group is modified to run a **`t3.medium`** (2 vCPU, 4 GB RAM) instead of `t3.micro`, it can serve as a unified staging/development host.

---

## 4. Recommended Architecture

To achieve high availability, fast developer velocity, automated CI/CD, and robust webhook processing, the following architecture is recommended.

```
                          ┌──────────────────────────────────────────────┐
                          │                INTERNET                      │
                          └──────────────────────┬───────────────────────┘
                                                 │
                                                 ▼
                          ┌──────────────────────────────────────────────┐
                          │          AWS Amplify (WEB_COMPUTE)           │
                          │   Next.js 16 App Router (Marketing SaaS)     │
                          │   - Stepper Wizards, Knowledge Uploader      │
                          │   - Analytics Dashboards (IG, FB, LinkedIn)  │
                          │   - Global CloudFront Edge Distribution      │
                          └──────────────────────┬───────────────────────┘
                                                 │
                                                 │ HTTPS Webhook API
                                                 │ Authorization: Bearer
                                                 ▼
 ┌────────────────────────┐       ┌──────────────────────────────────────┐
 │   n8n Automation Host  │       │         Amazon EC2 / ECS             │
 │  - AI Content Engine   ├──────►│   Agile Webhook Receiver & Backend   │
 │  - Social Sync Trigger │       │   FastAPI Outbound + Scheduler Loop  │
 └────────────────────────┘       └──────────────────┬───────────────────┘
                                                     │
                                                     │ Prisma & SQLAlchemy
                                                     │ Connection Pool
                                                     ▼
                                  ┌──────────────────────────────────────┐
                                  │      Amazon RDS PostgreSQL 16        │
                                  │   Target: db-dev-9 / Dedicated DB    │
                                  │   - Database: agile_sales_marketing  │
                                  │   - Isolated schemas and permissions │
                                  └──────────────────────────────────────┘
```

### 4.1 Frontend: AWS Amplify (`WEB_COMPUTE`)
- **Strategy**: Host the `frontend` on AWS Amplify under a dedicated App ID (or connected branch on `agile-frontend`).
- **Why Amplify?**:
  - Native Next.js 16 SSR / App Router support.
  - Automatic `STANDARD_8GB` build instances solve all compilation memory constraints.
  - Edge caching via Amazon CloudFront reduces latency to <50 ms globally.
  - Zero server management, patching, or OS maintenance.

### 4.2 Webhook Ingestion & Backend: Dedicated EC2 `t3.medium`
- **Strategy**: Provision a dedicated `t3.medium` instance (2 vCPUs, 4 GB RAM) running Ubuntu 24.04 LTS and Docker Compose.
- **Responsibilities**:
  - Runs the FastAPI application with background campaign schedulers (`SCHEDULER_ENABLED=True`).
  - Runs the containerized n8n workflow engine (or ngrok/production reverse proxy).
  - Handles `/api/webhooks/n8n/social-analytics` high-throughput data processing with memory headroom.

### 4.3 Database Strategy: Logical Database on Underutilized RDS
- **Strategy**: Do **NOT** use `agile-receivables-development` (`db.t3.micro`). Instead:
  - **Option 1 (Zero Added Cost)**: Create a dedicated logical database `agile_sales_marketing` inside **`db-dev-9`** (`db.t3.small`). CloudWatch telemetry shows `db-dev-9` has **1,150 MB (1.15 GB) of freeable memory** (over 57% idle capacity).
  - **Option 2 (Production Grade)**: Create the logical database inside `agile-receivables-production` (`db.t3.medium`, 4 GB RAM, 100 GB storage).
  - **Option 3 (Fully Isolated)**: Provision a new `db.t4g.small` (2 vCPUs, 2 GB RAM, Graviton3) dedicated exclusively to Marketing Automation.

---

## 5. Estimated Monthly Budget (us-east-2 On-Demand)

All estimates reflect current AWS on-demand rates in Region `us-east-2`:

### Scenario A: Recommended Cost-Optimized Setup (High Value / Low Overhead)

| Service Component | AWS Resource | Sizing / Configuration | Unit Rate | Est. Monthly Cost |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend Hosting** | AWS Amplify Hosting | 100 build min/mo + 15 GB data served | $0.01/min build + $0.15/GB | **$6.25** |
| **Backend & n8n Host** | Amazon EC2 | 1x `t3.medium` (Linux, On-Demand) | $0.0416 / hour | **$30.37** |
| **Compute Storage** | Amazon EBS (gp3) | 30 GB gp3 general-purpose SSD | $0.08 / GB-month | **$2.40** |
| **Relational Database** | Amazon RDS PostgreSQL | Logical DB in existing `db-dev-9` | $0.00 (reusing idle capacity) | **$0.00** |
| **Network & Egress** | Data Transfer | ~20 GB internet outbound | $0.09 / GB | **$1.80** |
| **Total Scenario A** | | | | **~$40.82 / month** |

### Scenario B: Fully Isolated Production Setup (Enterprise Tier)

| Service Component | AWS Resource | Sizing / Configuration | Unit Rate | Est. Monthly Cost |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend Hosting** | AWS Amplify Hosting | Production tier + Custom Domain | Pay-per-use | **$10.00** |
| **Backend Application** | Amazon EC2 (Docker) | 1x `t3.medium` (2 vCPU, 4 GB RAM) | $0.0416 / hour | **$30.37** |
| **Dedicated RDS DB** | Amazon RDS PostgreSQL | 1x `db.t4g.small` (2 vCPU, 2 GB RAM) | $0.034 / hour | **$24.82** |
| **RDS Storage** | Amazon EBS (gp3) | 40 GB gp3 storage | $0.115 / GB-month | **$4.60** |
| **Application Load Balancer**| AWS ALB | 1 ALB for SSL termination & routing | $0.0225 / hr + LCU | **$18.50** |
| **Total Scenario B** | | | | **~$88.29 / month** |

---

## 6. Next Steps for Deployment

We recommend executing deployment across 4 structured phases:

### Phase 1: Database Preparation & Migration
1. Connect to `db-dev-9` via bastion `stag-jump-ec2`.
2. Create logical database: `CREATE DATABASE agile_sales_marketing;`.
3. Create service user with least-privilege credentials:
   ```sql
   CREATE USER marketing_app WITH PASSWORD '...';
   GRANT ALL PRIVILEGES ON DATABASE agile_sales_marketing TO marketing_app;
   ```
4. Run Prisma schema migration:
   ```bash
   DATABASE_URL="postgresql://marketing_app:...@db-dev-9.c1u8uya4e50u.us-east-2.rds.amazonaws.com:5432/agile_sales_marketing" npx prisma db push
   ```

### Phase 2: Compute Host Configuration (Backend & n8n)
1. Provision EC2 `t3.medium` instance in `agile-receivables-development` VPC public subnet.
2. Configure security groups:
   - Inbound: Port 443/80 (HTTPS/HTTP), Port 22 (restricted to bastion `stag-jump-ec2`).
   - Outbound: All traffic via NAT instance.
3. Install Docker & Docker Compose.
4. Deploy FastAPI and n8n services with auto-restart policies.

### Phase 3: AWS Amplify Frontend Deployment
1. Connect the `Agile-Sales-Marketing` GitHub repository to AWS Amplify Console.
2. Select App Router framework and configure build settings:
   ```yaml
   version: 1
   frontend:
     phases:
       preBuild:
         commands:
           - npm ci
       build:
         commands:
           - npx prisma generate
           - npm run build
     artifacts:
       baseDirectory: .next
       files:
         - '**/*'
     cache:
       paths:
         - .next/cache/**/*
         - node_modules/**/*
   ```
3. Set Amplify Environment Variables:
   - `DATABASE_URL`: Connection string to RDS `agile_sales_marketing`.
   - `N8N_WEBHOOK_SECRET`: Secure 32-character bearer token.
   - `NEXT_PUBLIC_APP_URL`: Production Amplify domain.

### Phase 4: Verification & Webhook Testing
1. Send test payload from local/cloud n8n to `POST /api/webhooks/n8n/social-analytics`.
2. Verify upsert records in `Post` and `PostAnalytics` tables.
3. Validate `/marketing/social-media` UI graphs render Instagram and Facebook metrics accurately without latency.

---
*Report approved for submission to engineering leadership and management.*
