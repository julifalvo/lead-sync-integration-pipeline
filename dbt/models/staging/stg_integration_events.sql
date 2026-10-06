select
    external_id,
    status,
    detail,
    occurred_at
from {{ source('warehouse', 'integration_events') }}
