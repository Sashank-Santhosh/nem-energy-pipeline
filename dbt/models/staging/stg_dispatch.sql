-- One row per region x 5-minute interval: market run only (intervention = 0), latest copy wins.
with demand as (
    select regionid,
           strptime(settlementdate, '%Y/%m/%d %H:%M:%S') as interval_end,
           cast(totaldemand as double) as demand_mw
    from {{ source('raw', 'dispatch_regionsum') }}
    where intervention = '0'
    qualify row_number() over (partition by regionid, settlementdate order by loaded_at desc) = 1
),
price as (
    select regionid,
           strptime(settlementdate, '%Y/%m/%d %H:%M:%S') as interval_end,
           cast(rrp as double) as price_rrp
    from {{ source('raw', 'dispatch_price') }}
    where intervention = '0'
    qualify row_number() over (partition by regionid, settlementdate order by loaded_at desc) = 1
)
select d.regionid, d.interval_end, d.demand_mw, p.price_rrp
from demand d
left join price p using (regionid, interval_end)
