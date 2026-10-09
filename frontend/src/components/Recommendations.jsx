import { Section, Pill } from './ui'
import { fmtInt, fmtNum } from '../format'

// Recommendations — Phase 6 optimizer transfers, clearly labelled as
// recommendations (not executed moves).
export function Recommendations({ recommendations, loading, error, onRetry }) {
  const rec = recommendations
  const movements = rec?.movements ?? []

  return (
    <Section
      title="Optimizer recommendations"
      subtitle="Suggested resource transfers from the Phase 6 optimizer. These are recommendations, not executed moves."
      loading={loading}
      error={error}
      onRetry={onRetry}
      isEmpty={!loading && !error && movements.length === 0}
    >
      {rec?.feasible === false ? (
        <p className="muted">The optimizer reported no feasible solution for the current state.</p>
      ) : (
        <>
          <div className="stat-grid">
            <Pill label="Total units moved" value={fmtInt(rec?.total_resources_moved)} tone="primary" />
            <Pill label="Number of transfers" value={fmtInt(movements.length)} />
            <Pill label="Estimated movement cost" value={fmtNum(rec?.total_movement_cost)} />
            <Pill label="Remaining deficit (units)" value={fmtInt(rec?.remaining_deficit)} tone={rec?.remaining_deficit > 0 ? 'warn' : 'ok'} />
          </div>

          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">From (donor)</th>
                  <th scope="col">To (recipient)</th>
                  <th scope="col">Resource</th>
                  <th scope="col">Quantity</th>
                  <th scope="col">Distance (km)</th>
                  <th scope="col">Move cost</th>
                  <th scope="col">Reason</th>
                </tr>
              </thead>
              <tbody>
                {movements.map((m, i) => (
                  <tr key={i}>
                    <td className="label">{m.from_area}</td>
                    <td className="label">{m.to_area}</td>
                    <td>{m.resource.replace(/_/g, ' ')}</td>
                    <td className="num">{fmtInt(m.quantity)}</td>
                    <td className="num">{fmtNum(m.distance_km, 0)}</td>
                    <td className="num">{fmtNum(m.movement_cost)}</td>
                    <td className="reason">{m.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="footnote muted">
            “Move cost” is a prototype movement-cost estimate (units × distance × cost weight), not a real logistics price.
          </p>
        </>
      )}
    </Section>
  )
}

export default Recommendations
