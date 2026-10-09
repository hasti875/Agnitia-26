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
  const areas = useApiData(api.areas)
  const risk = useApiData(api.risk)
  const resources = useApiData(api.resources)
  const recommendations = useApiData(api.recommendations)
  const comparison = useApiData(api.comparison)
  const explanations = useApiData(api.explanations)
  const modelStatus = useApiData(api.modelStatus)

  const [reloadAll, setReloadAll] = useState(0)
  const [activeTab, setActiveTab] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')

  const overviewLoading = areas.loading || risk.loading || resources.loading
  const overviewError = [areas.error, risk.error, resources.error].filter(Boolean)[0] || null

  const scrollToSection = (id) => {
    setActiveTab(id)
    if (id === 'all') {
      window.scrollTo({ top: 0, behavior: 'smooth' })
      return
    }
    const elem = document.getElementById(id)
    if (elem) {
      elem.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  return (
    <div className="app">
      {/* Top Navbar Header (Matching Reference Image 1 & 3) */}
      <header className="app__header">
        <div className="app__header-inner">
          {/* Brand Logo & Title */}
          <a href="#" className="brand" onClick={(e) => { e.preventDefault(); scrollToSection('all'); }}>
            <div className="brand__logo">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              </svg>
            </div>
            <div>
              <h1 className="brand__title">
                ClimateRisk<span>Engine</span>
                <span className="brand__badge">MVP 1.0</span>
              </h1>
            </div>
          </a>

          {/* Navigation Links */}
          <nav>
            <ul className="nav-links">
              <li>
                <button
                  type="button"
                  className={`nav-link ${activeTab === 'all' ? 'is-active' : ''}`}
                  onClick={() => scrollToSection('all')}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
                  Home
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${activeTab === 'live-map' ? 'is-active' : ''}`}
                  onClick={() => scrollToSection('live-map')}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="1 6 1 22 8 18 15 22 23 18 23 2 15 6 8 2 1 6" /></svg>
                  Live Map
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${activeTab === 'resources' ? 'is-active' : ''}`}
                  onClick={() => scrollToSection('resources')}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" /></svg>
                  Resources
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${activeTab === 'optimizer' ? 'is-active' : ''}`}
                  onClick={() => scrollToSection('optimizer')}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></svg>
                  Optimizer
                </button>
              </li>
            </ul>
          </nav>

          {/* Right Header Controls */}
          <div className="header-actions">
            <div className="status-badge">
              <span className="status-dot" />
              <span>Operational</span>
            </div>

            <button
              type="button"
              className="btn btn--primary"
              onClick={() => {
                setReloadAll((n) => n + 1)
                areas.reload()
                risk.reload()
                resources.reload()
                recommendations.reload()
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M23 4v6h-6" /><path d="M1 20v-6h6" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></svg>
              Refresh Data
            </button>
          </div>
        </div>
      </header>

      {/* Main Dashboard Cards */}
      <main className="app__main" key={reloadAll}>
        {/* Hero Banner Section (Broad full-width inside main layout) */}
        <section className="hero-banner">
          <h1 className="hero-title">
            Smart Climate Risk Action for <span>Your Region</span>
          </h1>

          <p className="hero-subtitle">
            Monitor flood risk in real-time, detect equipment shortages, earn efficiency arbitrage, and navigate resources through cleaner, optimal logistics routes.
          </p>

          <div className="hero-search-wrap">
            <input
              type="text"
              placeholder="Enter Pincode (e.g. 452001) or Ward Name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <button type="button" className="hero-search-btn" onClick={() => scrollToSection('live-map')}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
              Check Risk
            </button>
          </div>

          <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
            <button type="button" className="btn" onClick={() => scrollToSection('live-map')}>
              View Live Map &rarr;
            </button>
            <button type="button" className="btn" onClick={() => scrollToSection('resources')}>
              Inspect Emergency Logistics
            </button>
          </div>
        </section>

        <Overview
          areas={areas.data}
          risk={risk.data}
          resources={resources.data}
          loading={overviewLoading}
          error={overviewError}
          onRetry={() => { areas.reload(); risk.reload(); resources.reload() }}
          updatedAt={risk.updatedAt || resources.updatedAt || areas.updatedAt}
        />

        <RiskMap
          areas={areas.data}
          risk={risk.data}
          resources={resources.data}
          recommendations={recommendations.data}
          loading={overviewLoading}
          error={overviewError}
          onRetry={() => { areas.reload(); risk.reload(); resources.reload(); recommendations.reload() }}
        />

        <ResourceAllocation
          resources={resources.data}
          loading={resources.loading}
          error={resources.error}
          onRetry={resources.reload}
        />

        <Recommendations
          recommendations={recommendations.data}
          loading={recommendations.loading}
          error={recommendations.error}
          onRetry={recommendations.reload}
        />

        <AreaRiskTable
          risk={risk.data}
          areas={areas.data}
          loading={risk.loading || areas.loading}
          error={risk.error || areas.error}
          onRetry={() => { risk.reload(); areas.reload() }}
        />

        <Comparison
          comparison={comparison.data}
          loading={comparison.loading}
          error={comparison.error}
          onRetry={comparison.reload}
        />

        <Explanations
          explanations={explanations.data}
          loading={explanations.loading}
          error={explanations.error}
          onRetry={explanations.reload}
        />
      </main>

      {/* Footer */}
      <footer className="app__footer">
        <p>
          Climate Risk Arbitrage Engine &middot; Decision support prototype estimates based on regional sensor telemetry and OR-Tools optimization.
        </p>
      </footer>
    </div>
  )
}
