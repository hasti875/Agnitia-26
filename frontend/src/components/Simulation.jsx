import { useState } from 'react'
import { Section } from './ui'
import { fmtNum, fmtPct } from '../format'
import api from '../api'

const RAINFALL_OPTIONS    = [-30, -20, -10, 0, 10, 20, 30]
const RIVER_OPTIONS       = [-10, 0, 10, 20]
const RESOURCE_OPTIONS    = [0, -10, -20, -30]

function RiskChangeBadge({ change }) {
  if (change === null || change === undefined) return null
  const abs = Math.abs(change).toFixed(1)
  if (change > 1)  return <span className="tag-badge tag-badge--red">↑ +{abs}</span>
  if (change < -1) return <span className="tag-badge tag-badge--ok">↓ -{abs}</span>
  return <span className="tag-badge tag-badge--teal">≈ {change > 0 ? '+' : ''}{change.toFixed(1)}</span>
}

function SliderRow({ label, value, options, onChange, unit = '%' }) {
  const sorted = [...options].sort((a, b) => a - b)
  const min = sorted[0]
  const max = sorted[sorted.length - 1]
  const step = sorted.length > 1 ? Math.abs(sorted[1] - sorted[0]) : 10

  // Snap raw slider value to nearest valid option
  function snapToValid(raw) {
    return sorted.reduce((prev, curr) =>
      Math.abs(curr - raw) < Math.abs(prev - raw) ? curr : prev
    )
  }

  const tone = value > 0 ? '#ef4444' : value < 0 ? '#10b981' : '#0d9488'
  return (
    <div style={{ marginBottom: '18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
        <label style={{ fontSize: '0.88rem', fontWeight: 600, color: '#334155' }}>{label}</label>
        <span style={{
          fontWeight: 800, fontSize: '0.95rem', color: tone,
          background: value === 0 ? '#f1f5f9' : value > 0 ? '#fee2e2' : '#dcfce7',
          padding: '2px 10px', borderRadius: '20px'
        }}>
          {value > 0 ? '+' : ''}{value}{unit}
        </span>
      </div>
      <input
        type="range"
        min={min} max={max}
        value={value}
        step={step}
        onChange={e => onChange(snapToValid(Number(e.target.value)))}
        style={{ width: '100%', accentColor: tone, cursor: 'pointer' }}
        list={`ticks-${label.replace(/\s+/g, '')}`}
      />
      <datalist id={`ticks-${label.replace(/\s+/g, '')}`}>
        {sorted.map(v => <option key={v} value={v} />)}
      </datalist>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#94a3b8', marginTop: '2px' }}>
        <span>{min}{unit}</span><span>0{unit}</span><span>{max > 0 ? '+' : ''}{max}{unit}</span>
      </div>
    </div>
  )
}

export function Simulation() {
  const [rainfall, setRainfall]   = useState(0)
  const [river, setRiver]         = useState(0)
  const [resources, setResources] = useState(0)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState(null)
  const [result, setResult]       = useState(null)

  const isBaseline = rainfall === 0 && river === 0 && resources === 0

  async function runSimulation() {
    // Always snap to nearest valid option before sending — guards against any
    // browser rounding that produces an off-step value like -18 instead of -20
    function snap(val, opts) {
      return opts.reduce((prev, curr) =>
        Math.abs(curr - val) < Math.abs(prev - val) ? curr : prev
      )
    }
    const safeRainfall   = snap(rainfall,  RAINFALL_OPTIONS)
    const safeRiver      = snap(river,     RIVER_OPTIONS)
    const safeResources  = snap(resources, RESOURCE_OPTIONS)

    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await api.simulate({
        rainfall_change_pct:              safeRainfall,
        river_level_change_pct:           safeRiver,
        resource_availability_change_pct: safeResources,
      })
      // Sync sliders to the snapped values so display stays consistent
      setRainfall(safeRainfall)
      setRiver(safeRiver)
      setResources(safeResources)
      setResult(data)
    } catch (e) {
      const msg = e?.message || 'Simulation failed'
      setError(msg.includes('422') || msg.includes('failed')
        ? 'Simulation failed — invalid parameter values. Values have been snapped to the nearest valid option. Please try again.'
        : msg)
    } finally {
      setLoading(false)
    }
  }

  function reset() {
    setRainfall(0); setRiver(0); setResources(0)
    setResult(null); setError(null)
  }

  const riskChanges   = result?.risk_changes ?? []
  const priorities    = result?.priority_changes ?? []
  const recChanges    = result?.recommendation_changes ?? {}
  const impact        = result?.estimated_impact ?? {}

  return (
    <Section
      id="simulate"
      title="What-If Scenario Simulator"
      subtitle="Adjust rainfall, river levels, and resource availability to see how risk and optimizer recommendations change."
    >
      <div className="callout callout--note">
        <strong>What-If Simulator:</strong> Adjusts rainfall, river levels, and resource availability then re-runs the full risk model → demand engine → OR-Tools optimizer pipeline. Results show how recommendations shift under each scenario.
      </div>

      {/* Controls */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '32px', margin: '20px 0', background: '#f8fafc', borderRadius: '14px', padding: '24px', border: '1px solid #e2e8f0' }}>
        <SliderRow
          label="Rainfall Change"
          value={rainfall}
          options={RAINFALL_OPTIONS}
          onChange={v => { setRainfall(v); setResult(null) }}
        />
        <SliderRow
          label="River Level Change"
          value={river}
          options={RIVER_OPTIONS}
          onChange={v => { setRiver(v); setResult(null) }}
        />
        <SliderRow
          label="Resource Availability"
          value={resources}
          options={RESOURCE_OPTIONS}
          onChange={v => { setResources(v); setResult(null) }}
        />
      </div>

      <div style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
        <button
          type="button"
          className="btn btn--primary"
          onClick={runSimulation}
          disabled={loading}
          style={{ minWidth: '160px', fontWeight: 700 }}
        >
          {loading ? '⏳ Running…' : isBaseline ? '▶ Run Baseline' : '▶ Run Scenario'}
        </button>
        {result && (
          <button type="button" className="btn btn--outline" onClick={reset}>
            ↺ Reset
          </button>
        )}
      </div>

      {error && (
        <div style={{ background: '#fee2e2', border: '1px solid #fca5a5', color: '#991b1b', borderRadius: '8px', padding: '10px 16px', marginBottom: '16px', fontSize: '0.88rem' }}>
          ⚠ {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div>
          {/* Scenario summary headline */}
          <div style={{ background: '#0d9488', color: '#fff', borderRadius: '12px', padding: '14px 20px', marginBottom: '20px', display: 'flex', gap: '40px', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: '0.75rem', opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Scenario</div>
              <div style={{ fontSize: '1rem', fontWeight: 800 }}>
                Rain {rainfall > 0 ? '+' : ''}{rainfall}% · River {river > 0 ? '+' : ''}{river}% · Resources {resources}%
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Impact Change</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 800 }}>
                {impact.baseline_total_impact !== undefined ? (
                  <>
                    {fmtNum(impact.baseline_total_impact, 3)} → {fmtNum(impact.scenario_total_impact, 3)}
                    {' '}
                    <span style={{ fontSize: '0.88rem', opacity: 0.85 }}>
                      ({impact.absolute_impact_change > 0 ? '+' : ''}{fmtNum(impact.absolute_impact_change, 3)})
                    </span>
                  </>
                ) : 'N/A'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Areas Affected</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 800 }}>{riskChanges.length} zones</div>
            </div>
          </div>

          {/* Risk Changes Table */}
          {riskChanges.length > 0 && (
            <div style={{ marginBottom: '24px' }}>
              <h4 style={{ margin: '0 0 10px', color: '#0f172a', fontSize: '0.95rem', fontWeight: 700 }}>
                Risk Changes by Area
              </h4>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Area</th>
                      <th style={{ textAlign: 'right' }}>Baseline Risk</th>
                      <th style={{ textAlign: 'right' }}>Scenario Risk</th>
                      <th>Change</th>
                      <th>Risk Level</th>
                    </tr>
                  </thead>
                  <tbody>
                    {riskChanges.map((r, i) => (
                      <tr key={i} style={{ background: Math.abs(r.risk_change) > 5 ? '#fff7ed' : undefined }}>
                        <td className="label">{r.area_name}</td>
                        <td className="num">{fmtNum(r.baseline_predicted_risk)}</td>
                        <td className="num" style={{ fontWeight: 700 }}>{fmtNum(r.scenario_predicted_risk)}</td>
                        <td><RiskChangeBadge change={r.risk_change} /></td>
                        <td>
                          <span style={{ fontSize: '0.82rem' }}>
                            {r.baseline_risk_level} → <strong>{r.scenario_risk_level}</strong>
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Priority Changes */}
          {priorities.length > 0 && (
            <div style={{ marginBottom: '24px' }}>
              <h4 style={{ margin: '0 0 10px', color: '#0f172a', fontSize: '0.95rem', fontWeight: 700 }}>
                Priority Shifts
              </h4>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                {priorities.map((p, i) => (
                  <div key={i} style={{
                    background: p.more_urgent ? '#fee2e2' : '#dcfce7',
                    border: `1px solid ${p.more_urgent ? '#fca5a5' : '#86efac'}`,
                    borderRadius: '10px', padding: '10px 14px', minWidth: '180px'
                  }}>
                    <div style={{ fontWeight: 700, fontSize: '0.88rem', color: p.more_urgent ? '#991b1b' : '#166534' }}>
                      {p.more_urgent ? '🔺 More Urgent' : '🔻 Less Urgent'}
                    </div>
                    <div style={{ fontWeight: 600, fontSize: '0.85rem', marginTop: '3px' }}>{p.area_name}</div>
                    <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: '2px' }}>
                      Risk: {fmtNum(p.baseline_predicted_risk)} → {fmtNum(p.scenario_predicted_risk)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recommendation Changes */}
          {((recChanges.added_movements?.length > 0) || (recChanges.removed_movements?.length > 0) || (recChanges.changed_movements?.length > 0)) && (
            <div style={{ marginBottom: '24px' }}>
              <h4 style={{ margin: '0 0 10px', color: '#0f172a', fontSize: '0.95rem', fontWeight: 700 }}>
                Optimizer Recommendation Changes
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
                {recChanges.added_movements?.length > 0 && (
                  <div style={{ background: '#dcfce7', border: '1px solid #86efac', borderRadius: '10px', padding: '12px' }}>
                    <div style={{ fontWeight: 700, color: '#166534', marginBottom: '6px' }}>➕ New Transfers ({recChanges.added_movements.length})</div>
                    {recChanges.added_movements.map((m, i) => (
                      <div key={i} style={{ fontSize: '0.8rem', color: '#14532d', margin: '3px 0' }}>
                        {m.quantity}× {m.resource.replace(/_/g,' ')} · {m.from_area} → {m.to_area}
                      </div>
                    ))}
                  </div>
                )}
                {recChanges.removed_movements?.length > 0 && (
                  <div style={{ background: '#fee2e2', border: '1px solid #fca5a5', borderRadius: '10px', padding: '12px' }}>
                    <div style={{ fontWeight: 700, color: '#991b1b', marginBottom: '6px' }}>➖ Cancelled Transfers ({recChanges.removed_movements.length})</div>
                    {recChanges.removed_movements.map((m, i) => (
                      <div key={i} style={{ fontSize: '0.8rem', color: '#7f1d1d', margin: '3px 0' }}>
                        {m.quantity}× {m.resource.replace(/_/g,' ')} · {m.from_area} → {m.to_area}
                      </div>
                    ))}
                  </div>
                )}
                {recChanges.changed_movements?.length > 0 && (
                  <div style={{ background: '#fef3c7', border: '1px solid #fde68a', borderRadius: '10px', padding: '12px' }}>
                    <div style={{ fontWeight: 700, color: '#92400e', marginBottom: '6px' }}>✏️ Changed Quantities ({recChanges.changed_movements.length})</div>
                    {recChanges.changed_movements.map((m, i) => (
                      <div key={i} style={{ fontSize: '0.8rem', color: '#78350f', margin: '3px 0' }}>
                        {m.resource.replace(/_/g,' ')} · {m.from_area} → {m.to_area}: {m.baseline_quantity} → {m.scenario_quantity}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              {!recChanges.added_movements?.length && !recChanges.removed_movements?.length && !recChanges.changed_movements?.length && (
                <p style={{ color: '#0d9488', fontWeight: 600, fontSize: '0.88rem' }}>✓ Optimizer recommendations unchanged under this scenario.</p>
              )}
            </div>
          )}

          {/* No changes at all */}
          {isBaseline && riskChanges.every(r => r.risk_change === 0) && (
            <p style={{ color: '#0d9488', fontWeight: 600 }}>✓ Baseline confirmed — no changes from current state.</p>
          )}
        </div>
      )}
    </Section>
  )
}

export default Simulation
