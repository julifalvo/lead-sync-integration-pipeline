-- Per-source performance: which lead sources (webform, ad_campaign, ...)
-- have the healthiest sync rate, useful for deciding where to invest
-- marketing spend or which upstream integration needs attention.
with received as (
    select external_id, source from {{ ref('stg_raw_leads') }}
),

synced as (
    select external_id from {{ ref('stg_leads') }}
),

dead_lettered as (
    select distinct external_id
    from {{ ref('stg_integration_events') }}
    where status = 'error'
)

select
    received.source,
    count(distinct received.external_id) as total_received,
    count(distinct synced.external_id) as total_synced,
    count(distinct dead_lettered.external_id) as total_dead_lettered,
    round(
        100.0 * count(distinct dead_lettered.external_id) / nullif(count(distinct received.external_id), 0),
        2
    ) as dead_letter_rate_pct
from received
left join synced on synced.external_id = received.external_id
left join dead_lettered on dead_lettered.external_id = received.external_id
group by 1
order by total_received desc
