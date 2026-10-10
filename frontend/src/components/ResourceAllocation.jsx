import { Section, RiskBadge, ProgressBar, ShortfallPill } from './ui'
import { fmtInt } from '../format'

export function ResourceAllocation({ resources, loading, error, onRetry }) {
  const rows = resources?.resources ?? []

  // Group rows by area, preserving API order of first appearance.
  const byArea = {}
  const order = []
  for (const r of rows) {
    if (!byArea[r.area_id]) {
      byArea[r.area_id] = {
        name: r.area_name,
        rows: {},
        totalDeficit: 0,
        totalSurplus: 0,
        riskLevel: r.risk_level || 'LOW',
      }
      order.push(r.area_id)
    }
    byArea[r.area_id].rows[r.resource] = r
    byArea[r.area_id].totalDeficit += (r.deficit || 0)
    byArea[r.area_id].totalSurplus += (r.surplus || 0)
    // Use the highest risk_level seen across resource rows for this area
    if (r.risk_level) byArea[r.area_id].riskLevel = r.risk_level
  }

  // Resource columns present in the data.
  const resourceTypes = []
  for (const r of rows) if (!resourceTypes.includes(r.resource)) resourceTypes.push(r.resource)

  return (
    <Section
      id="resources"
      title="Resource coordination"
      subtitle="EMERGENCY LOGISTICS · Regional inventory, live shortages, and automated fulfillment tracking."
      loading={loading}
      error={error}
      onRetry={onRetry}
      isEmpty={!loading && !error && rows.length === 0}
    >
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th scope="col" style={{ width: '18%' }}>Region</th>
              <th scope="col" style={{ width: '15%' }}>Risk Category</th>
              {resourceTypes.map((res) => (
                <th key={res} scope="col" style={{ width: '18%' }}>
                  {res.replace(/_/g, ' ')}
                </th>
              ))}
              <th scope="col" style={{ width: '14%', textAlign: 'right' }}>Shortfall Status</th>
            </tr>
          </thead>
          <tbody>
            {order.map((aid) => {
              const areaData = byArea[aid]
              const totalDef = areaData.totalDeficit
              const totalSur = areaData.totalSurplus
              const liveRisk = areaData.riskLevel || 'LOW'

              return (
                <tr key={aid}>
                  <td className="label" style={{ fontSize: '0.92rem' }}>
                    {areaData.name}
                  </td>
                  <td>
                    <RiskBadge level={liveRisk} />
                  </td>
                  {resourceTypes.map((res) => {
                    const cell = areaData.rows[res]
                    if (!cell) return <td key={res} className="muted">—</td>

                    const isDef = cell.deficit > 0
                    const status = isDef ? 'danger' : 'normal'
                    return (
                      <td key={res}>
                        <ProgressBar
                          current={cell.current}
                          max={cell.required}
                          status={status}
                        />
                      </td>
                    )
                  })}
                  <td style={{ textAlign: 'right' }}>
                    <ShortfallPill deficit={totalDef} surplus={totalSur} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="footnote muted">
        Inventory units represent deployed vs. required field capacity. Automated deficits dictate Phase 6 OR-Tools optimizer movements.
      </p>
    </Section>
  )
}

export default ResourceAllocation
