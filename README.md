# Sellna.ai — Sales Agentic AI

> Enterprise-grade multi-agent B2B sales intelligence platform built with FastAPI, PostgreSQL, Qdrant, and OpenAI.

---

## Project Structure

```
sellna.ai/                          ← Project root (run everything from here)
│
├── main.py                         ← Root entry point (Sales AI app)
├── config.py                       ← Scraper engine config (env-overridable)
├── scraper.py                      ← Core async scraping engine (httpx + Playwright)
├── extractor.py                    ← HTML → structured data parser
├── scraper_standalone.py           ← Lightweight scraper-only FastAPI app (port 8000)
│
├── scrapping_module/               ← Social media scraping
│   ├── social.py                   ← LinkedIn (Google SERP) + Instagram multi-strategy
│   ├── stealth.py                  ← Playwright anti-detection patches
│   └── engines/                    ← Platform-specific engine classes
│       ├── base.py
│       ├── linkedin.py
│       └── instagram.py
│
├── app/                            ← Sales Agentic AI FastAPI application
│   ├── main.py                     ← FastAPI app, lifespan, middleware, routers
│   ├── config/settings.py          ← Pydantic Settings (reads from .env)
│   │
│   ├── core/
│   │   ├── logging.py              ← structlog configured logger
│   │   ├── security.py             ← JWT auth, role-based access
│   │   └── dependencies.py        ← FastAPI Depends() injectors
│   │
│   ├── api/v1/                     ← All REST endpoints
│   │   ├── company.py              ← POST /company/input
│   │   ├── competitors.py          ← POST /competitors/discover
│   │   ├── icp.py                  ← POST /icp/generate
│   │   ├── personas.py             ← POST /personas/generate
│   │   ├── outreach.py             ← POST /outreach/generate
│   │   ├── analytics.py            ← GET  /analytics/performance
│   │   └── pipeline.py             ← POST /pipeline/run  ← FULL E2E
│   │
│   ├── agents/                     ← 9 stateless AI agents
│   │   ├── domain_agent.py         ← LLM market analysis
│   │   ├── competitor_agent.py     ← LLM competitor discovery
│   │   ├── web_agent.py            ← Uses scraper.py + extractor.py
│   │   ├── cleaning_agent.py       ← Text normalization
│   │   ├── gap_analysis_agent.py   ← RAG: embed → search → LLM
│   │   ├── icp_agent.py            ← LLM ICP generation
│   │   ├── persona_agent.py        ← LLM + RAG personas
│   │   ├── outreach_agent.py       ← LLM cold email / LinkedIn / call
│   │   └── optimization_agent.py   ← Feedback-driven optimization
│   │
│   ├── services/
│   │   ├── llm_service.py          ← OpenAI-compatible async client
│   │   ├── embedding_service.py    ← OpenAI or SentenceTransformers
│   │   ├── scraping_service.py     ← Bridge: app ↔ scrapping_module
│   │   └── rag_service.py          ← Index / Retrieve / Generate
│   │
│   ├── db/
│   │   ├── postgres.py             ← SQLAlchemy 2.x async engine + ORM models
│   │   ├── vector_store.py         ← Qdrant / FAISS abstraction
│   │   └── repositories/           ← Typed CRUD for each entity
│   │
│   ├── pipelines/sales_pipeline.py ← Full 8-stage orchestrator
│   ├── schemas/                    ← Pydantic data contracts
│   └── utils/                      ← text_cleaning, similarity
│
├── tests/                          ← pytest suite (SQLite in-memory, mocked LLM)
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml          ← API + PostgreSQL + Redis + Qdrant
│
├── static/                         ← Scraper UI static files
├── requirements.txt                ← Single unified requirements
├── pyproject.toml                  ← Project metadata + pytest/mypy config
└── .env.example                    ← Copy to .env and fill in your keys
```

---

## Quick Start

### 1. Set up environment

```powershell
# From project root: d:\Git Repos\sellna.ai\
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure secrets

```powershell
Copy-Item .env.example .env
# Open .env and set OPENAI_API_KEY and DATABASE_URL
```

### 3. Start infrastructure (Docker)

```powershell
cd docker
docker compose up -d postgres redis qdrant
cd ..
```

### 4. Run the Sales AI backend

```powershell
# From project root:
python main.py
# → Sales AI API at http://localhost:8001/docs
```

Or run just the Sales AI app:
```powershell
uvicorn app.main:app --port 8001 --reload
```

Or just the legacy scraper UI:
```powershell
uvicorn scraper_standalone:app --port 8000 --reload
```

---

## API Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/pipeline/run` | **Full E2E pipeline** |
| `POST` | `/api/v1/company/input` | Submit company + domain analysis |
| `GET`  | `/api/v1/company/{id}/analysis` | Get analysis |
| `POST` | `/api/v1/competitors/discover/{id}` | Discover competitors |
| `POST` | `/api/v1/competitors/scrape/{id}` | Scrape competitor websites |
| `POST` | `/api/v1/icp/generate` | Generate ICPs |
| `POST` | `/api/v1/personas/generate` | Generate personas |
| `POST` | `/api/v1/outreach/generate` | Generate outreach content |
| `POST` | `/api/v1/outreach/feedback` | Submit engagement feedback |
| `GET`  | `/api/v1/analytics/performance/{id}` | Performance stats |
| `POST` | `/api/v1/analytics/optimize/{id}` | AI optimization recommendations |
| `POST` | `/api/auth/token` | Get JWT token |
| `GET`  | `/health` | Health check |
| `POST` | `/api/scrape` | Raw URL scraper (standalone) |
| `POST` | `/api/social/scrape` | Social media scraper (standalone) |

---

## Running Tests

```powershell
# From project root:
pytest tests/ -v
# No real DB or API key needed — uses SQLite + mocked LLM
```

---

## Key Design Decisions

- **One codebase, one `requirements.txt`** — no more nested subfolder
- **`config.py`** at root = scraper engine config (env-overridable)
- **`app/config/settings.py`** = Pydantic Settings for the FastAPI layer
- **Imports always work** when `uvicorn` / `pytest` is run from the project root
- **`scrapping_module/`** is completely unchanged — `app/services/scraping_service.py` bridges it
