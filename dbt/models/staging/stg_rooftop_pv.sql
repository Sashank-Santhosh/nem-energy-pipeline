-- Half-hourly rooftop PV estimate; MEASUREMENT preferred over SATELLITE, then latest copy.
select regionid,
       strptime(interval_datetime, '%Y/%m/%d %H:%M:%S') as period_end,
       cast(power as double) as rooftop_pv_mw,
       type as estimate_type
from {{ source('raw', 'rooftop_pv_actual') }}
qualify row_number() over (
    partition by regionid, interval_datetime
    order by (type = 'MEASUREMENT') desc, loaded_at desc) = 1
