with fuel as (
    select regionid, interval_end,
           sum(mw) filter (where fuel = 'solar') as solar_mw,
           sum(mw) filter (where fuel = 'wind') as wind_mw,
           sum(mw) filter (where fuel = 'coal') as coal_mw,
           sum(mw) filter (where fuel = 'gas') as gas_mw,
           sum(mw) filter (where fuel = 'hydro') as hydro_mw,
           sum(mw) filter (where fuel = 'battery') as battery_mw,
           sum(mw) filter (where fuel = 'other') as other_mw
    from {{ ref('stg_fuel_mix') }}
    group by 1, 2
),
base as (
    select d.*,
           -- the half-hour (period end) that contains this 5-minute interval
           time_bucket(interval 30 minute, d.interval_end - interval 5 minute)
               + interval 30 minute as pv_period_end
    from {{ ref('stg_dispatch') }} d
)
select b.regionid || '|' || strftime(b.interval_end, '%Y-%m-%d %H:%M') as interval_key,
       b.regionid,
       b.interval_end,
       b.price_rrp,
       b.demand_mw,
       pv.rooftop_pv_mw,
       pv.rooftop_pv_mw is not null and b.interval_end <> b.pv_period_end as rooftop_pv_interpolated,
       f.solar_mw, f.wind_mw, f.coal_mw, f.gas_mw, f.hydro_mw, f.battery_mw, f.other_mw,
       b.price_rrp < 0 as is_negative_price
from base b
left join {{ ref('stg_rooftop_pv') }} pv
       on pv.regionid = b.regionid and pv.period_end = b.pv_period_end
left join fuel f
       on f.regionid = b.regionid and f.interval_end = b.interval_end
