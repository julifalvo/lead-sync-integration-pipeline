-- Daily funnel: leads received (bronze) vs. successfully synced (silver) vs.
-- dead-lettered, by day. Lets you answer "did yesterday's ingestion spike
-- also spike our CRM failure rate?" in one query instead of grepping logs.
with received as (
    select
        date_trunc('day', received_at)::date as day,
        external_id
    from {{ ref('stg_raw_leads') }}
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
    received.day,
    count(distinct received.external_id) as leads_received,
    count(distinct synced.external_id) as leads_synced,
    count(distinct dead_lettered.external_id) as leads_dead_lettered,
    round(
        100.0 * count(distinct dead_lettered.external_id) / nullif(count(distinct received.external_id), 0),
        2
    ) as dead_letter_rate_pct
from received
left join synced on synced.external_id = received.external_id
left join dead_lettered on dead_lettered.external_id = received.external_id
group by 1
order by 1
