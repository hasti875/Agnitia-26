# Climate Risk Arbitrage Engine — Frontend (Phase 11)

React dashboard for the Climate Risk Arbitrage Engine. It is a **prototype
decision-support UI** built on **synthetic data**. All figures are estimates
for demonstration only; they are not official disaster forecasts, do not
represent lives saved, and do not establish real-world risk reduction.

## Stack

- React 19 + Vite
- Plain CSS (no UI framework) — responsive, accessible, dark theme
- Vitest + jsdom + Testing Library for lightweight tests

## Setup

```bash
npm install
```

The backend base URL is configurable via the Vite env var `VITE_API_BASE_URL`
(see `.env` / `.env.example`). The default is `/api`, which the Vite dev
server proxies to the FastAPI backend on `http://127.0.0.1:8000` (see
`vite.config.js`). For a deployed frontend, set `VITE_API_BASE_URL` to the
absolute backend origin, e.g. `VITE_API_BASE_URL=https://api.example.com`.

## Scripts

| Command           | Description                          |
| ----------------- | ------------------------------------ |
| `npm run dev`     | Start the Vite dev server (port 5173) |
| `npm run build`   | Production build to `dist/`          |
| `npm run preview` | Preview the production build         |
| `npm test`        | Run the Vitest suite (single run)    |
| `npm run test:watch` | Run Vitest in watch mode          |
| `npm run lint`    | Run oxlint                           |

## Dashboard sections

1. **Overview** — monitored-area count, areas by risk category, total units
   available, total deficit/surplus, last-updated time.
2. **Area risk** — all eight areas with predicted risk (0–100), category
   (marker + text label, not color alone), population, density, vulnerability.
   Sortable columns.
3. **Resource allocation** — current vs required inventory by area and
   resource type; deficits highlighted; units only.
4. **Optimizer recommendations** — recommended transfers (donor, recipient,
   resource, quantity, distance, movement cost) with totals. Labelled as
   recommendations, not executed moves.
5. **Impact comparison** — fixed vs optimized estimated prototype
   risk-impact metric, absolute and percentage reduction. Clearly labelled as
   an estimated metric on synthetic data.
6. **Geographic risk map** — coordinate-validated area markers, risk legend,
   selected-area details, and optional illustrative transfer connections.
7. **Explanations** — expandable cards for area-risk, shortage, transfer, and
   allocation-comparison explanations from `/explanations`.

## API endpoints used

`/areas`, `/risk`, `/resources`, `/recommendations`, `/comparison`,
`/explanations`. All calls go through the reusable service in `src/api.js`.
Each section fetches independently so one failing endpoint shows an error in
its own section without crashing the rest of the dashboard.

## Manual verification procedure

Because a browser is not available in the CI/sandbox environment, verify the
dashboard manually:

1. Start the backend:
   ```bash
   python -m uvicorn backend.api.main:app --port 8000
   ```
2. Start the frontend:
   ```bash
   cd frontend
   npm run dev
   ```
3. Open `http://localhost:5173` in a browser.
4. Confirm all seven sections render with live data (no "Loading…" spinners
   remain, no error panels).
5. Confirm the Overview shows 8 areas, category chips, and resource totals.
6. Confirm the Area risk table lists all 8 areas with risk scores and
   category badges (marker + text).
7. Confirm Resource allocation highlights deficits in red.
8. Confirm Recommendations lists transfers with donor/recipient/resource/
   quantity/distance/cost and totals.
9. Confirm Impact comparison shows fixed vs optimized values, absolute and
   percentage reduction, and the "estimated metric, synthetic data" callout.
10. Confirm Explanations cards expand/collapse and show the plain-language
    text from the API.
11. Test partial failure: stop the backend, click "Refresh" — each section
    should show its own error panel with a "Try again" button, and the
    dashboard should not crash.
12. Test loading: with the backend running, hard-refresh — spinners should
    appear briefly then resolve to data.

## Testing

```bash
npm test
```

Covers:
- `api.js` — error handling (non-2xx, network failure), success path, POST body.
- `format.js` — number formatting, risk-category metadata.
- `useApiData` hook — loading, success, error capture.
- `Section` component — loading, error (with retry), and healthy states.

## Geographic risk map (Phase 12)

The **Geographic risk map** appears between Overview and the area-risk table.
It joins area, risk, and resource data by `area_id`, colors markers by risk
category, and shows a detail panel when an area is selected. The dashed transfer
connections use recommendation endpoint area names to find the corresponding
area coordinates. They are straight-line illustrations, not road routes or
executed transfers. The checkbox toggles them on and off.

- Coordinates must be finite numeric latitude/longitude values within legal
  ranges. The `(0, 0)` null-island sentinel is excluded, and excluded areas are
  listed below the map.
- Missing risk is shown as unavailable/unknown. Missing resource rows are shown
  as **Resource data unavailable**, not as a real zero deficit.
- If recommendations fail, markers and area details remain available while
  transfer connections show an unavailable message.
- OpenStreetMap tiles require an internet connection. If tiles fail, the map
  shows a non-blocking warning while area details remain available.

React Leaflet and Leaflet are frontend dependencies. Install them with the
other frontend dependencies using `npm install` before running the app.

### Map verification

The `RiskMap.test.jsx` suite tests joining, coordinate validation, null-island
exclusion, route resolution, map centering, loading/error/empty states, marker
and detail rendering, missing data, route toggling, and tile-error messaging.
The component tests mock React Leaflet and therefore do not validate actual
Leaflet rendering or live OpenStreetMap tile delivery; verify those in a real
browser using the manual procedure above.
