{{ config(severity='warn') }}
-- Warn if any region has a gap of more than 60 minutes in its latest 7 days of data.
with x as (
    select regionid, interval_end,
           interval_end - lag(interval_end) over (partition by regionid order by interval_end) as gap
    from {{ ref('fct_region_interval') }}
    qualify interval_end >= max(interval_end) over () - interval 7 day
)
select * from x where gap > interval 60 minute
