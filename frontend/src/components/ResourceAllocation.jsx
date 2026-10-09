import { Section, DeficitTag, SurplusTag } from './ui'
import { fmtInt } from '../format'

// ResourceAllocation — current vs required inventory per area and resource,
// with shortages highlighted. Units only (no currency/distance here).
export function ResourceAllocation({ resources, loading, error, onRetry }) {
  const rows = resources?.resources ?? []

  // Group rows by area, preserving API order of first appearance.
  const byArea = {}
  const order = []
  for (const r of rows) {
    if (!byArea[r.area_id]) { byArea[r.area_id] = { name: r.area_name, rows: [] }; order.push(r.area_id) }
    byArea[r.area_id].rows.push(r)
  }

  // Resource columns present in the data.
  const resourceTypes = []
  for (const r of rows) if (!resourceTypes.includes(r.resource)) resourceTypes.push(r.resource)

  const totalDeficitRows = rows.filter((r) => r.deficit > 0).length

  return (
    <Section
      title="Resource allocation"
      subtitle="Current inventory vs required inventory by area and resource type."
      loading={loading}
      error={error}
      onRetry={onRetry}
      isEmpty={!loading && !error && rows.length === 0}
    >
      <p className="muted" aria-live="polite">
        {totalDeficitRows > 0
          ? `${totalDeficitRows} area/resource combination(s) are in deficit (highlighted).`
          : 'No deficits are currently calculated.'}
      </p>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th scope="col" rowSpan="2">Area</th>
              {resourceTypes.map((res) => (
                <th key={res} scope="colgroup" colSpan="4" className="th-group">
                  {res.replace(/_/g, ' ')}
                </th>
              ))}
            </tr>
            <tr>
              {resourceTypes.map((res) => (
                <FragmentSub key={res} />
              ))}
            </tr>
          </thead>
          <tbody>
            {order.map((aid) => (
              <tr key={aid}>
                <th scope="row" className="label">{byArea[aid].name}</th>
                {resourceTypes.map((res) => {
                  const cell = byArea[aid].rows.find((r) => r.resource === res)
                  return (
                    <ResourceCells key={res} cell={cell} />
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="footnote muted">
        All values are resource units. “Required” is the Phase 5 computed requirement; deficit = required − current (≥ 0); surplus = current − required (≥ 0).
      </p>
    </Section>
  )
}

function FragmentSub() {
  return (
    <>
      <th scope="col">Current</th>
      <th scope="col">Required</th>
      <th scope="col">Surplus</th>
      <th scope="col">Deficit</th>
    </>
  )
}

function ResourceCells({ cell }) {
  if (!cell) return <td className="muted" colSpan="4">—</td>
  return (
    <>
      <td className="num">{fmtInt(cell.current)}</td>
      <td className="num">{fmtInt(cell.required)}</td>
      <td className="num"><SurplusTag value={cell.surplus} /></td>
      <td className="num"><DeficitTag value={cell.deficit} /></td>
    </>
  )
}

export default ResourceAllocation
