"""sellna.ai — Sales Agentic AI

Single project entry point.

Usage:
    # Sales Agentic AI (full backend — port 8001)
    uvicorn main:sales_app --port 8001 --reload

    # Or the standalone scraper UI (port 8000)
    uvicorn main:scraper_app --port 8000 --reload

    # Run both apps (recommended in dev)
    python main.py

Import the correct app object:
    from main import sales_app   ← FastAPI with all AI agents
    from main import scraper_app ← Lightweight scraper-only UI
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Sales Agentic AI — main app (all agents, pipeline, APIs)
# ---------------------------------------------------------------------------
from app.main import app as sales_app  # noqa: F401  (the primary app)

# ---------------------------------------------------------------------------
# Scraper standalone UI — kept for backward compat / raw scrape testing
# ---------------------------------------------------------------------------
from scraper_standalone import app as scraper_app  # noqa: F401


if __name__ == "__main__":
    import uvicorn

    print(
        "\n"
        "╔══════════════════════════════════════════════════╗\n"
        "║          Sellna.ai — Sales Agentic AI            ║\n"
        "╠══════════════════════════════════════════════════╣\n"
        "║  Sales AI API  →  http://localhost:8001/docs     ║\n"
        "║  Scraper UI    →  http://localhost:8000          ║\n"
        "╚══════════════════════════════════════════════════╝\n"
    )

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info",
    )
