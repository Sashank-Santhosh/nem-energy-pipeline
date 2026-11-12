-- Half-hourly mean demand, only for half-hours with all six 5-minute intervals present.
select regionid,
       time_bucket(interval 30 minute, interval_end - interval 5 minute)
           + interval 30 minute as period_end,
       avg(demand_mw) as demand_mw
from {{ ref('stg_dispatch') }}
group by 1, 2
having count(*) = 6
