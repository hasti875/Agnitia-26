import { useState } from 'react'
import api from './api'
import useApiData from './useApiData'
import Overview from './components/Overview'
import AreaRiskTable from './components/AreaRiskTable'
import ResourceAllocation from './components/ResourceAllocation'
import Recommendations from './components/Recommendations'
import Comparison from './components/Comparison'
import Explanations from './components/Explanations'
import RiskMap from './components/RiskMap'

export default function App() {
  // Each section fetches independently so one failure never breaks the rest.
  const areas = useApiData(api.areas)
  const risk = useApiData(api.risk)
  const resources = useApiData(api.resources)
  const recommendations = useApiData(api.recommendations)
  const comparison = useApiData(api.comparison)
  const explanations = useApiData(api.explanations)
  const modelStatus = useApiData(api.modelStatus)

  const [reloadAll, setReloadAll] = useState(0)

  const overviewLoading = areas.loading || risk.loading || resources.loading
  const overviewError = [areas.error, risk.error, resources.error].filter(Boolean)[0] || null

  const activeModel = modelStatus.data?.active_model
  const modelWarning = modelStatus.data?.warning
  const modelSource = modelStatus.data?.models?.[activeModel]?.source_data

  const dataTag = activeModel === 'real_data_model'
    ? 'real-world data'
    : 'synthetic data'

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__header-inner">
          <div>
            <h1 className="app__title">Climate Risk Arbitrage Engine</h1>
            <p className="app__tag">Prototype decision-support dashboard · {dataTag}</p>
          </div>
          <button type="button" className="btn" onClick={() => setReloadAll((n) => n + 1)}>
            Refresh
          </button>
        </div>
      </header>

      {modelWarning ? (
        <div className="model-warning" role="alert">
          <strong>Model status:</strong> {modelWarning}
        </div>
      ) : null}

      <main className="app__main" key={reloadAll}>
        <Overview
          areas={areas.data}
          risk={risk.data}
          resources={resources.data}
          loading={overviewLoading}
          error={overviewError}
          onRetry={() => { areas.reload(); risk.reload(); resources.reload() }}
          updatedAt={risk.updatedAt || resources.updatedAt || areas.updatedAt}
        />
        <RiskMap areas={areas.data} risk={risk.data} resources={resources.data} recommendations={recommendations.data} loading={overviewLoading} error={overviewError} onRetry={() => { areas.reload(); risk.reload(); resources.reload(); recommendations.reload() }} />
        <AreaRiskTable risk={risk.data} areas={areas.data} loading={risk.loading || areas.loading} error={risk.error || areas.error} onRetry={() => { risk.reload(); areas.reload() }} />
        <ResourceAllocation resources={resources.data} loading={resources.loading} error={resources.error} onRetry={resources.reload} />
        <Recommendations recommendations={recommendations.data} loading={recommendations.loading} error={recommendations.error} onRetry={recommendations.reload} />
        <Comparison comparison={comparison.data} loading={comparison.loading} error={comparison.error} onRetry={comparison.reload} />
        <Explanations explanations={explanations.data} loading={explanations.loading} error={explanations.error} onRetry={explanations.reload} />
      </main>

      <footer className="app__footer">
        <p>
          All figures are prototype decision-support estimates.
          {activeModel === 'real_data_model'
            ? ' Based on real-world historical data. Predictions require independent validation before operational use.'
            : ' Based on a synthetic dataset for a hackathon demo. They are not official disaster forecasts, do not represent lives saved, and do not establish real-world risk reduction.'}
        </p>
        {modelSource ? <p className="muted">Data source: {modelSource}</p> : null}
      </footer>
    </div>
  )
}
