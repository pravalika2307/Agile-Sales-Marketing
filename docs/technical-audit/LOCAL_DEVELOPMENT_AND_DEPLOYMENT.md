# Local Development, Environment Setup, & Deployment Guide

**Platform:** Agile Sales & Marketing  
**Audit Date:** October 2026  
**Auditor Roles:** Senior DevOps Engineer, Site Reliability Engineer  
**Document Purpose:** Complete runbook for onboarding engineers to configure local environments, execute database migrations, start dev servers, run test suites, and deploy to staging/production.

---

## 1. System Prerequisites

Before configuring the project locally, ensure the following runtimes are installed:
* **Operating System:** Windows 10/11, macOS, or Linux (Ubuntu 22.04+).
* **Node.js:** `v20.x` or `v22.x` LTS with `npm 10+`.
* **Python:** Python `3.11` or `3.13` with `pip`.
* **Database:** PostgreSQL `15` or `16` (local service or Docker container).

---

## 2. Backend Local Setup Instructions

### Step 2.1: Clone and Navigate
```bash
cd D:\Agile-Sales-Marketing\backend
```

### Step 2.2: Create and Activate Virtual Environment
```bash
# Windows PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### Step 2.3: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2.4: Environment File Configuration
Create a `.env` file in `backend/` by copying `.env.example`:
```bash
cp .env.example .env
```
Update configuration parameters:
* `DATABASE_URL`: `postgresql+psycopg://postgres:password@localhost:5432/agile_sales_marketing`
* `SECRET_KEY`: Generate a random 32+ character key.
* `EMAIL_PROVIDER_TYPE`: Use `mock` for safe local offline development.

### Step 2.5: Run Database Migrations
Apply all 15 Alembic revisions to initialize database schemas and indexes:
```bash
alembic upgrade head
```

### Step 2.6: Start Backend Dev Server
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
* Interactive API Documentation will be available at: `http://localhost:8000/docs`
* Health probe: `http://localhost:8000/health`

---

## 3. Frontend Local Setup Instructions

### Step 3.1: Navigate to Frontend Directory
```bash
cd D:\Agile-Sales-Marketing\frontend
```

### Step 3.2: Install NPM Dependencies
```bash
npm install
```

### Step 3.3: Start Frontend Dev Server
```bash
npm run dev
```
The application will launch at: `http://localhost:3000`

---

## 4. Quality Verification & Test Execution

### 4.1. Run Backend Automated Test Suite
```bash
cd D:\Agile-Sales-Marketing\backend
pytest tests/ -v
```
*(Runs against an in-memory SQLite database without touching PostgreSQL.)*

### 4.2. Run Frontend Typecheck
```bash
cd D:\Agile-Sales-Marketing\frontend
npx tsc --noEmit
```

### 4.3. Run Frontend Production Build Validation
```bash
npm run build
```

---

## 5. Deployment Architecture & Production Considerations

### 5.1. Backend Deployment (FastAPI)
* **Production ASGI Server:** Run Uvicorn behind Gunicorn workers:
  ```bash
  gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
  ```
* **Reverse Proxy:** Terminate SSL (HTTPS) at NGINX or AWS Application Load Balancer (ALB).
* **Database Connection Pooling:** Set pool size to 20-50 connections with `pool_pre_ping=True` in SQLAlchemy.

### 5.2. Frontend Deployment (Next.js)
* **Standalone Build:** Next.js can be deployed via Docker or Node.js runtime (`npm start`).
* **Environment Variables:** Set `NEXT_PUBLIC_API_URL` to point to the production backend gateway domain.

### 5.3. Safe Rollback Procedures
* If a release fails, roll back frontend assets via blue/green deployment.
* Alembic migrations support downgrade operations:
  ```bash
  alembic downgrade -1
  ```
