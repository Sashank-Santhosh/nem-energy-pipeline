with x as (
    select *,
           cast(interval_end - interval 5 minute as date) as trading_date,
           hour(interval_end - interval 5 minute) as hr
    from {{ ref('fct_region_interval') }}
)
select regionid,
       trading_date,
       min(demand_mw) as min_demand_mw,
       max(demand_mw) as peak_demand_mw,
       avg(demand_mw) filter (where hr between 18 and 19)
           - avg(demand_mw) filter (where hr between 11 and 13) as midday_dip_mw,
       count(*) filter (where is_negative_price) as negative_price_intervals,
       avg((coalesce(solar_mw, 0) + coalesce(rooftop_pv_mw, 0))
           / nullif(demand_mw + coalesce(rooftop_pv_mw, 0), 0)) as solar_share
from x
group by 1, 2
