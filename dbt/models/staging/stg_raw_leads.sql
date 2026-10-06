-- One row per external_id: the earliest raw submission we ever saw for it,
-- which is where we get `source` for leads that were later dead-lettered
-- and therefore never made it into warehouse.leads.
select distinct on (external_id)
    external_id,
    source,
    received_at
from {{ source('warehouse', 'raw_lead_events') }}
order by external_id, received_at asc
