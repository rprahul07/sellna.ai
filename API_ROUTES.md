## Backend API routes (FastAPI)

Base prefix: `/api/v1`

### UI configuration (frontend must not hardcode datasets)
- `GET /ui/sidebar`
- `GET /ui/landing`
- `GET /ui/company-input`
- `GET /ui/auth-copy`
- `GET /ui/personas`

### Company intelligence
- `POST /company/input`
- `GET /company/`
- `GET /company/{company_id}/analysis`

### Pipeline orchestration
- `POST /pipeline/run` (async; Celery or in-process fallback)
- `GET /pipeline/status/{job_id}`
- `GET /pipeline/result/{job_id}`
- `POST /pipeline/run/sync` (dev/testing)

### Competitors
- `POST /competitors/discover/{company_id}`
- `GET /competitors/{company_id}`
- `POST /competitors/scrape/{company_id}`

### ICPs
- `POST /icp/generate`
- `GET /icp/{company_id}`

### Personas
- `POST /personas/generate` (supports optional `icp_id`)
- `GET /personas/{company_id}`

### Outreach
- `POST /outreach/generate`
- `POST /outreach/feedback`
- `GET /outreach/{company_id}`

### Analytics
- `GET /analytics/performance/{company_id}` (includes `by_channel` + `weekly`)
- `POST /analytics/optimize/{company_id}`

### Dashboard aggregation
- `GET /dashboard/summary`
- `GET /dashboard/activity?limit=20`

## Frontend data flow (high level)

All module pages key off a **real** `companyId` produced by the pipeline:

1. `Company Intel` (`/company`)
   - Submits `POST /pipeline/run`
   - Polls `GET /pipeline/status/{job_id}`
   - Fetches `GET /pipeline/result/{job_id}` and stores `companyId`

2. `Competitors` (`/competitors`)
   - Lists: `GET /competitors/{companyId}`
   - Actions: `POST /competitors/discover/{companyId}`, `POST /competitors/scrape/{companyId}`

3. `ICP Generator` (`/icp`)
   - Lists: `GET /icp/{companyId}`
   - Generate: `POST /icp/generate`

4. `Personas` (`/personas`)
   - Lists: `GET /personas/{companyId}`
   - Generate: `POST /personas/generate`

5. `Outreach` (`/outreach`)
   - Lists: `GET /outreach/{companyId}`
   - Generate: `POST /outreach/generate` (requires a `persona_id`)

6. `Analytics` (`/analytics`)
   - Performance: `GET /analytics/performance/{companyId}`

7. `Dashboard` (`/`)
   - Stats: `GET /dashboard/summary`
   - Activity feed: `GET /dashboard/activity`

