# Climate Risk Arbitrage Engine

> A hackathon-grade system that predicts regional flood risk, detects emergency
> resource deficits, and optimises the reallocation of limited resources
> (pumps, rescue teams, medical kits) across 8 regions in Madhya Pradesh.

---

## Problem Statement

Climate risks such as floods shift between regions over time, while emergency
resources are finite and often misallocated.  
This system answers three questions:

1. **Where** will flood risk be highest in the next 6 hours?
2. **Which** regions have too few resources to cope?
3. **How** should resources be moved to minimise total unmet need?

---

## Architecture

```
Synthetic Climate + Resource Data
         │
         ▼
  Data Processing (Pandas / NumPy)
         │
         ▼
  Feature Engineering (lag · rolling · trend)
         │
         ▼
  Risk Forecast (RandomForestRegressor)
         │
         ▼
  Resource Deficit Detection
         │
         ▼
  OR-Tools Optimisation (CP-SAT)
         │
         ▼
  Scenario Simulation (what-if)
         │
         ▼
  Fixed vs Optimised Comparison + Explainer
         │
         ▼
  FastAPI  ←──────────────────────►  React Dashboard
```

All data is **synthetic and local** — no paid APIs required.

---

## Repository Layout

```
climate-risk-arbitrage/
├── backend/
│   ├── main.py               ← FastAPI application entry point
│   ├── requirements.txt
│   ├── data/                 ← synthetic CSVs (generated in Phase 2)
│   ├── forecasting/          ← ML model training + inference
│   ├── risk/                 ← deficit detection, risk scoring
│   ├── optimization/         ← OR-Tools allocation solver
│   ├── simulation/           ← what-if scenario engine
│   ├── analysis/             ← comparator + explanation engine
│   └── utils/                ← shared helpers
├── frontend/                 ← React + Vite + Tailwind (Phase 6)
├── docs/                     ← architecture diagrams, notes
└── README.md
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Data processing | Pandas, NumPy |
| Machine learning | scikit-learn (RandomForestRegressor) |
| Optimisation | Google OR-Tools (CP-SAT) |
| API server | FastAPI + Uvicorn |
| Model persistence | Joblib |
| Data validation | Pydantic v2 |
| Frontend | React 18, Vite, Tailwind CSS |
| Charts | Recharts |
| Map | Leaflet / React-Leaflet |

---

## Regions Covered

Indore · Ujjain · Dewas · Dhar · Ratlam · Mandsaur · Mhow · Sehore

---

## Resource Types

| # | Resource |
|---|---|
| 1 | Pumps |
| 2 | Rescue teams |
| 3 | Medical kits |

---

## Prerequisites

- Python 3.11 or newer — download from https://www.python.org/downloads/
- Node.js 20 or newer (needed for Phase 6 frontend)

---

## Backend — Installation (Windows)

Open **PowerShell** in the project root and run:

```powershell
# 1. Create a virtual environment
python -m venv .venv

# 2. Activate it
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r backend\requirements.txt
```

> If PowerShell blocks script execution, run this first (once):
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

---

## Starting the FastAPI Server (Windows)

With the virtual environment active:

```powershell
cd backend
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at:

| URL | Purpose |
|---|---|
| http://127.0.0.1:8000/api/health | Health check |
| http://127.0.0.1:8000/docs | Swagger UI (interactive API docs) |
| http://127.0.0.1:8000/redoc | ReDoc API reference |

---

## Quick Health Check

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health"
```

Expected response:

```json
{
  "status": "ok",
  "project": "Climate Risk Arbitrage Engine"
}
```

---

## Development Phases

| Phase | Description | Status |
|---|---|---|
| 1 | Project setup + FastAPI skeleton | ✅ Done |
| 2 | Synthetic data generation + feature engineering | ⏳ |
| 3 | Risk forecast model (RandomForest) | ⏳ |
| 4 | Deficit detection + OR-Tools optimisation | ⏳ |
| 5 | Scenario simulation + comparator + explainer | ⏳ |
| 6 | Full FastAPI routing | ⏳ |
| 7 | React dashboard | ⏳ |

---

## License

MIT — built for hackathon demonstration purposes.
