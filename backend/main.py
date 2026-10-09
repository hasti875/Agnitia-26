"""
Climate Risk Arbitrage Engine — FastAPI entry point.

Phase 1: skeleton with health check only.
Subsequent phases will register routers from:
  - forecasting/
  - risk/
  - optimization/
  - simulation/
  - analysis/
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Climate Risk Arbitrage Engine",
    description=(
        "Predicts regional flood risk, detects resource deficits, "
        "and optimises emergency resource allocation using OR-Tools."
    ),
    version="0.1.0",
)

# Allow the React dev server (port 5173) to call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["system"])
def health_check():
    """Returns service status. Used by the frontend to confirm the API is up."""
    return {
        "status": "ok",
        "project": "Climate Risk Arbitrage Engine",
    }
