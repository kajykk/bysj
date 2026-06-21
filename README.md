# Depression Warning System

## Overview

This repository contains a full-stack warning and intervention system with a FastAPI backend and a Vue 3 frontend.

## Project structure

- `backend/` FastAPI application, domain logic, tests, and database setup
- `frontend/` Vue 3 application, pages, components, and UI tests
- `scripts/` helper scripts for reports and test orchestration

## Prerequisites

- Python 3.11+
- Node.js 20+
- npm 10+

## Local setup

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Configuration

Main runtime settings are loaded from backend environment variables and frontend Vite runtime configuration.

Common backend settings include:
- database connection
- Redis URL
- CORS origins
- seed data toggle
- upload directory

Create a local `.env` file for non-default values when needed.

## Database and migration

The backend initializes tables on startup. If Alembic migrations are added later, keep migration scripts under the backend migration directory and apply them before starting the service in production.

## Testing

### Backend

```bash
npm run test:backend
```

Runs backend integration checks and refreshes the backend test overview.

### Frontend

```bash
npm run test:frontend
```

Runs frontend end-to-end checks and refreshes the overview report.

### Full suite

```bash
npm run test:all
```

Runs the backend and frontend test workflow together.

## Coverage

Coverage reporting is expected to be produced separately by backend and frontend test jobs and merged in CI.

## Deployment

Recommended deployment order:
1. Install backend and frontend dependencies
2. Run tests and coverage checks
3. Build frontend assets
4. Start the backend service
5. Serve the frontend through the chosen web server or static hosting layer

## Test workflow

- `npm run test:backend` runs the backend harness integration test.
- `npm run test:frontend` runs Playwright and refreshes the overview report.
- `npm run test:all` runs backend, refreshes the overview, runs Playwright, then refreshes the overview again.
