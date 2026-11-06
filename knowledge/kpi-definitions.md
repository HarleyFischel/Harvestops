# KPI definitions

HarvestOps stores operational timestamps in UTC and applies the selected planned-departure date, customer, product, and facility scope consistently.

- Shipment volume: count of shipments in scope.
- Fill rate: shipped quantity divided by ordered quantity.
- On-time rate: on-time departures divided by closed shipments; open and cancelled shipments are excluded from the denominator.
- Freight cost: sum of shipment freight cost in scope.
- Production output: sum of seeded production-run output in the selected facility/product/date scope. A customer filter is a shipment-scope selector used to identify matching facility/product activity; production is not attributed to an individual customer because production runs do not carry customer ownership.
- Labor productivity: production output divided by labor-record hours in the same scope. Labor is aggregated by production run before joining so each run's output is counted once even when it has multiple labor records.

These definitions use synthetic portfolio data.
