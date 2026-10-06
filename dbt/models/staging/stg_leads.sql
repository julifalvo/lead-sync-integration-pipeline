select
    external_id,
    first_name,
    last_name,
    email,
    company,
    source,
    submitted_at,
    synced_at
from {{ source('warehouse', 'leads') }}
